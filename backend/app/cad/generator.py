from __future__ import annotations

import json
import math
import re
from pathlib import Path

from backend.app.models import ConnectorDimensions, ConnectorParams, InputMode, UnknownDimension

try:
    import cadquery as cq
    from cadquery import exporters

    CADQUERY_AVAILABLE = True
    CADQUERY_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - depends on local CAD environment
    cq = None
    exporters = None
    CADQUERY_AVAILABLE = False
    CADQUERY_IMPORT_ERROR = str(exc)


DOWNLOAD_KINDS = {
    "step": "connector.step",
    "stp": "connector.stp",
    "dxf": "connector.dxf",
    "stl": "connector.stl",
    "glb": "connector.glb",
    "params": "params.json",
}


def build_params(mode: InputMode, text: str | None, attachment_name: str | None) -> ConnectorParams:
    normalized_text = (text or "").strip()
    pin_count = _extract_pin_count(normalized_text) or 16
    pin_rows = 2 if pin_count > 8 else 1
    pin_pitch = _extract_pitch(normalized_text) or 2.54

    columns = math.ceil(pin_count / pin_rows)
    cavity_length = max(12.0, (columns - 1) * pin_pitch + 8.0)
    cavity_width = 7.8 if pin_rows == 1 else max(8.0, (pin_rows - 1) * pin_pitch + 6.5)
    overall_length = cavity_length + 18.0
    overall_width = cavity_width + 8.0
    overall_height = 9.0

    source = "text_heuristic" if mode == InputMode.text and normalized_text else "uploaded_file_unverified"
    unknown_reason = (
        "MVP 未做图纸/图像尺寸识别，上传文件仅作为附件保存。"
        if mode != InputMode.text
        else "文本描述不足以确认制造级尺寸。"
    )

    unknowns = [
        UnknownDimension(name="manufacturer_exact_spec", label="厂家精确规格", reason=unknown_reason),
        UnknownDimension(name="tolerance", label="公差", reason="MVP 没有数据表或工程图公差来源。"),
        UnknownDimension(name="material", label="材料", reason="输入未提供材料牌号。"),
        UnknownDimension(name="contact_geometry", label="端子真实几何", reason="白模只表达针位阵列，不编造端子细节。"),
    ]

    title = _title_from_text(normalized_text) if normalized_text else "通用矩形连接器白模"
    return ConnectorParams(
        title=title,
        description="通用矩形连接器 MVP 参数化白模，含外壳、孔腔、针位、锁扣、安装孔和倒角/圆角。",
        source=source,
        input_mode=mode,
        input_text=normalized_text or None,
        attachment_name=attachment_name,
        dimensions=ConnectorDimensions(
            overall_length=round(overall_length, 2),
            overall_width=round(overall_width, 2),
            overall_height=overall_height,
            cavity_length=round(cavity_length, 2),
            cavity_width=round(cavity_width, 2),
            cavity_depth=4.4,
            pin_count=pin_count,
            pin_rows=pin_rows,
            pin_pitch=pin_pitch,
            pin_diameter=1.0,
            mount_hole_diameter=3.1,
            mount_hole_spacing=round(overall_length - 7.0, 2),
            lock_width=round(min(cavity_length * 0.45, 18.0), 2),
            lock_depth=2.0,
            lock_height=2.4,
            fillet_radius=0.9,
            chamfer=0.45,
        ),
        unknowns=unknowns,
    )


def generate_artifacts(params: ConnectorParams, output_dir: Path) -> dict[str, Path]:
    if not CADQUERY_AVAILABLE:
        raise RuntimeError(f"CadQuery is not available: {CADQUERY_IMPORT_ERROR}")

    output_dir.mkdir(parents=True, exist_ok=True)
    model = build_connector_model(params.dimensions)

    step_path = output_dir / DOWNLOAD_KINDS["step"]
    stp_path = output_dir / DOWNLOAD_KINDS["stp"]
    stl_path = output_dir / DOWNLOAD_KINDS["stl"]
    dxf_path = output_dir / DOWNLOAD_KINDS["dxf"]
    glb_path = output_dir / DOWNLOAD_KINDS["glb"]
    params_path = output_dir / DOWNLOAD_KINDS["params"]

    exporters.export(model, str(step_path), exportType="STEP")
    exporters.export(model, str(stp_path), exportType="STEP")
    exporters.export(model, str(stl_path), exportType="STL")
    write_dxf(params.dimensions, dxf_path)
    write_params(params, params_path)
    write_glb_from_stl(stl_path, glb_path)

    return {
        "step": step_path,
        "stp": stp_path,
        "stl": stl_path,
        "dxf": dxf_path,
        "glb": glb_path,
        "params": params_path,
    }


def build_connector_model(dim: ConnectorDimensions):
    shell = (
        cq.Workplane("XY")
        .box(dim.overall_length, dim.overall_width, dim.overall_height)
        .edges("|Z")
        .fillet(dim.fillet_radius)
        .edges("#Z")
        .chamfer(dim.chamfer)
    )

    cavity_cut = (
        cq.Workplane("XY")
        .center(0, 0)
        .box(dim.cavity_length, dim.cavity_width, dim.cavity_depth)
        .translate((0, 0, dim.overall_height / 2 - dim.cavity_depth / 2 + 0.05))
    )
    model = shell.cut(cavity_cut)

    lock = (
        cq.Workplane("XY")
        .box(dim.lock_width, dim.lock_depth, dim.lock_height)
        .translate((0, dim.overall_width / 2 + dim.lock_depth / 2 - 0.2, dim.overall_height / 2 + dim.lock_height / 2 - 0.2))
        .edges("|Z")
        .fillet(0.35)
    )
    model = model.union(lock)

    for x in (-dim.mount_hole_spacing / 2, dim.mount_hole_spacing / 2):
        hole = (
            cq.Workplane("XY")
            .circle(dim.mount_hole_diameter / 2)
            .extrude(dim.overall_height + 1.0)
            .translate((x, 0, -0.5))
        )
        model = model.cut(hole)

    pins = _pin_positions(dim)
    for x, y in pins:
        pin = (
            cq.Workplane("XY")
            .circle(dim.pin_diameter / 2)
            .extrude(1.35)
            .translate((x, y, dim.overall_height / 2 - 0.2))
        )
        model = model.union(pin)

    return model


def write_dxf(dim: ConnectorDimensions, path: Path) -> None:
    left = -dim.overall_length / 2
    right = dim.overall_length / 2
    bottom = -dim.overall_width / 2
    top = dim.overall_width / 2
    cavity_left = -dim.cavity_length / 2
    cavity_right = dim.cavity_length / 2
    cavity_bottom = -dim.cavity_width / 2
    cavity_top = dim.cavity_width / 2

    entities: list[str] = []
    entities.extend(_dxf_rect(left, bottom, right, top, "OUTLINE"))
    entities.extend(_dxf_rect(cavity_left, cavity_bottom, cavity_right, cavity_top, "CAVITY"))
    for x in (-dim.mount_hole_spacing / 2, dim.mount_hole_spacing / 2):
        entities.extend(_dxf_circle(x, 0, dim.mount_hole_diameter / 2, "MOUNT"))
    for x, y in _pin_positions(dim):
        entities.extend(_dxf_circle(x, y, dim.pin_diameter / 2, "PINS"))

    path.write_text(
        "\n".join(
            [
                "0",
                "SECTION",
                "2",
                "ENTITIES",
                *entities,
                "0",
                "ENDSEC",
                "0",
                "EOF",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_params(params: ConnectorParams, path: Path) -> None:
    path.write_text(json.dumps(params.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


def write_glb_from_stl(stl_path: Path, glb_path: Path) -> None:
    try:
        import trimesh

        mesh = trimesh.load_mesh(stl_path)
        mesh.export(glb_path)
    except Exception:
        glb_path.write_bytes(_minimal_glb())


def _extract_pin_count(text: str) -> int | None:
    if not text:
        return None
    patterns = [
        r"(\d+)\s*(?:pin|pins|p|针|针位)",
        r"(\d+)\s*[xX]\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            if len(match.groups()) == 2 and match.group(2):
                return int(match.group(1)) * int(match.group(2))
            return int(match.group(1))
    return None


def _extract_pitch(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*mm", text, flags=re.IGNORECASE)
    if match:
        value = float(match.group(1))
        if 0.5 <= value <= 10:
            return value
    return None


def _title_from_text(text: str) -> str:
    return text[:80] if text else "通用矩形连接器白模"


def _pin_positions(dim: ConnectorDimensions) -> list[tuple[float, float]]:
    rows = dim.pin_rows
    columns = math.ceil(dim.pin_count / rows)
    positions: list[tuple[float, float]] = []
    for index in range(dim.pin_count):
        row = index // columns
        col = index % columns
        x = (col - (columns - 1) / 2) * dim.pin_pitch
        y = (row - (rows - 1) / 2) * dim.pin_pitch
        positions.append((x, y))
    return positions


def _dxf_rect(left: float, bottom: float, right: float, top: float, layer: str) -> list[str]:
    return [
        *_dxf_line(left, bottom, right, bottom, layer),
        *_dxf_line(right, bottom, right, top, layer),
        *_dxf_line(right, top, left, top, layer),
        *_dxf_line(left, top, left, bottom, layer),
    ]


def _dxf_line(x1: float, y1: float, x2: float, y2: float, layer: str) -> list[str]:
    return ["0", "LINE", "8", layer, "10", f"{x1:.3f}", "20", f"{y1:.3f}", "11", f"{x2:.3f}", "21", f"{y2:.3f}"]


def _dxf_circle(x: float, y: float, r: float, layer: str) -> list[str]:
    return ["0", "CIRCLE", "8", layer, "10", f"{x:.3f}", "20", f"{y:.3f}", "40", f"{r:.3f}"]


def _minimal_glb() -> bytes:
    # Valid GLB 2.0 with an empty JSON scene. Used only when optional trimesh export is unavailable.
    json_chunk = b'{"asset":{"version":"2.0"},"scenes":[{}],"scene":0}'
    padding = (4 - (len(json_chunk) % 4)) % 4
    json_chunk += b" " * padding
    total_length = 12 + 8 + len(json_chunk)
    return b"glTF" + (2).to_bytes(4, "little") + total_length.to_bytes(4, "little") + len(json_chunk).to_bytes(4, "little") + b"JSON" + json_chunk
