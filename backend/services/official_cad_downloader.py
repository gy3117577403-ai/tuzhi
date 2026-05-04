from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from cadquery import exporters, importers

from services.connector_params import ConnectorCadParams


def can_use_official_cad(cad_source: dict) -> bool:
    cad_url = cad_source.get("cad_url") or ""
    return cad_source.get("source_type") in {"official_cad", "third_party"} and bool(cad_url) and not cad_source.get("requires_manual_url")


def download_official_cad(cad_source: dict, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    original_path = output_dir / "official_original.step"
    model_step = output_dir / "model.step"
    model_stl = output_dir / "model.stl"
    drawing_dxf = output_dir / "drawing.dxf"

    source_path = _fetch_to_path(cad_source.get("cached_file_path") or cad_source["cad_url"], original_path)
    shutil.copyfile(source_path, model_step)
    _try_export_stl(model_step, model_stl)
    if not drawing_dxf.exists():
        drawing_dxf.write_text(_minimal_dxf(), encoding="utf-8")
    return {
        "official_original.step": original_path,
        "model.step": model_step,
        "model.stl": model_stl,
        "drawing.dxf": drawing_dxf,
    }


def write_official_params(params: ConnectorCadParams, output_dir: Path) -> Path:
    payload = params.model_dump()
    payload["generation_files"] = {"step": "model.step", "stl": "model.stl", "dxf": "drawing.dxf"}
    path = output_dir / "params.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _fetch_to_path(cad_url: str, target: Path) -> Path:
    parsed = urlparse(cad_url)
    if parsed.scheme == "file":
        raw_path = parsed.path.lstrip("/")
        source = Path(raw_path)
        if not source.is_absolute():
            source = Path(__file__).resolve().parents[1] / source.relative_to("backend") if raw_path.startswith("backend/") else Path.cwd() / source
        if not source.exists():
            raise FileNotFoundError(f"Official CAD local file not found: {source}")
        shutil.copyfile(source, target)
        return target
    if parsed.scheme in {"http", "https"}:
        urllib.request.urlretrieve(cad_url, target)
        return target
    source = Path(cad_url)
    if not source.is_absolute():
        source = Path.cwd() / source
    if not source.exists():
        raise FileNotFoundError(f"Official CAD file not found: {source}")
    shutil.copyfile(source, target)
    return target


def _try_export_stl(step_path: Path, stl_path: Path) -> None:
    try:
        shape = importers.importStep(str(step_path))
        exporters.export(shape, str(stl_path), exportType="STL")
    except Exception:
        # STEP is still the authoritative downloadable artifact.
        return


def _minimal_dxf() -> str:
    return "\n".join(["0", "SECTION", "2", "ENTITIES", "0", "ENDSEC", "0", "EOF", ""])
