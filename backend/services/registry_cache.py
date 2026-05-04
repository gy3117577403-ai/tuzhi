from __future__ import annotations

import hashlib
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException

from services.domain_policy import classify_source_url
from services.json_store import atomic_write_json, read_json
from services.registry_history import append_registry_event
from services.registry_store import DATA_ROOT, load_registry, save_registry

CACHE_ROOT = DATA_ROOT / "registry_cache"


def cache_registry_cad_file(item: dict[str, Any]) -> dict[str, Any]:
    item_id = item["id"]
    cache_dir = CACHE_ROOT / item_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    ext = _extension(item.get("file_type") or item.get("cad_url") or "step")
    original_path = cache_dir / f"original.{ext}"
    _fetch_to_path(item["cad_url"], original_path)
    sha256 = _sha256(original_path)
    domain = classify_source_url(item.get("source_url") or item.get("cad_url"))
    metadata = {
        "registry_item_id": item_id,
        "part_number": item.get("part_number"),
        "manufacturer": item.get("manufacturer"),
        "cached_at": _now(),
        "source_url": item.get("source_url", ""),
        "cad_url": item.get("cad_url", ""),
        "original_filename": _original_filename(item.get("cad_url", "")),
        "cached_filename": original_path.name,
        "file_type": item.get("file_type", ext),
        "file_size_bytes": original_path.stat().st_size,
        "sha256": sha256,
        "source_category": domain.get("category", "unknown"),
        "domain": domain.get("domain", ""),
    }
    metadata_path = cache_dir / "metadata.json"
    atomic_write_json(metadata_path, metadata)
    append_registry_event(item_id, "cached", "system", before=item, after={**item, **_cache_fields(original_path, metadata_path, metadata)}, note="Registry CAD file cached.")
    return {"cached_file_path": str(original_path), "cache_metadata_path": str(metadata_path), **metadata}


def get_cached_registry_file(item_id: str) -> dict[str, Any]:
    cache_dir = CACHE_ROOT / item_id
    metadata_path = cache_dir / "metadata.json"
    metadata = read_json(metadata_path, {})
    cached_filename = metadata.get("cached_filename")
    cached_file = cache_dir / cached_filename if cached_filename else None
    return {
        "registry_item_id": item_id,
        "cache_status": "cached" if cached_file and cached_file.exists() else "missing",
        "cached_file_path": str(cached_file) if cached_file else "",
        "cache_metadata_path": str(metadata_path) if metadata_path.exists() else "",
        "metadata": metadata,
    }


def validate_cached_file(item: dict[str, Any]) -> bool:
    cached_file = Path(item.get("cached_file_path") or "")
    if not cached_file.exists():
        return False
    expected = item.get("sha256")
    return bool(expected) and _sha256(cached_file) == expected


def refresh_registry_cache(item_id: str) -> dict[str, Any]:
    data = load_registry()
    for index, item in enumerate(data.get("items", [])):
        if item.get("id") != item_id:
            continue
        before = dict(item)
        cache = cache_registry_cad_file(item)
        updated = {
            **item,
            **_cache_fields(Path(cache["cached_file_path"]), Path(cache["cache_metadata_path"]), cache),
            "sha256": cache["sha256"],
            "file_size_bytes": cache["file_size_bytes"],
            "updated_at": _now(),
        }
        data["items"][index] = updated
        save_registry(data)
        append_registry_event(item_id, "updated", "system", before=before, after=updated, note="Registry cache metadata refreshed.")
        return updated
    raise HTTPException(status_code=404, detail="Registry item not found")


def remove_registry_cache(item_id: str) -> None:
    shutil.rmtree(CACHE_ROOT / item_id, ignore_errors=True)


def _cache_fields(cached_file: Path, metadata_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "cached_file_path": str(cached_file),
        "cache_metadata_path": str(metadata_path),
        "cache_status": "cached",
        "cached_at": metadata["cached_at"],
    }


def _fetch_to_path(cad_url: str, target: Path) -> Path:
    parsed = urlparse(cad_url)
    if parsed.scheme == "file":
        raw_path = parsed.path.lstrip("/")
        source = Path(raw_path)
        if not source.is_absolute():
            source = Path(__file__).resolve().parents[1] / source.relative_to("backend") if raw_path.startswith("backend/") else Path.cwd() / source
        if not source.exists():
            raise FileNotFoundError(f"CAD file not found: {source}")
        shutil.copyfile(source, target)
        return target
    if parsed.scheme in {"http", "https"}:
        urllib.request.urlretrieve(cad_url, target)
        return target
    source = Path(cad_url)
    if not source.is_absolute():
        source = Path.cwd() / source
    if not source.exists():
        raise FileNotFoundError(f"CAD file not found: {source}")
    shutil.copyfile(source, target)
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extension(value: str) -> str:
    suffix = Path(value).suffix.lower().lstrip(".")
    if suffix in {"step", "stp", "stl", "dxf", "iges", "igs"}:
        return "step" if suffix == "stp" else suffix
    return "step" if value.lower() in {"step", "stp"} else value.lower().strip(".")


def _original_filename(cad_url: str) -> str:
    parsed = urlparse(cad_url)
    return Path(parsed.path).name or "model.step"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
