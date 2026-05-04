from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import cadquery as cq
from cadquery import exporters

from services.cad_generator import (
    normalize_cad_params,
    write_engineering_dxf,
    write_params_json,
)
from services.connector_params import (
    PARAMETRIC_DISCLAIMER,
    PROVISIONAL_WARNING,
    ConnectorCadParams,
)
from services.cad_generator import cavity_positions as pin_cavity_positions

BACKGROUND_DISCLAIMER = "Appearance-proximate CAD for preview only; not manufacturing-grade or official supplier data."


def _to_norm_dict(params: ConnectorCadParams) -> dict[str, Any]:
    d = normalize_cad_params(params)
    d["template_name"] = params.template_name or (params.appearance_pipeline or {}).get("template_name")
    d["appearance_confidence"] = params.appearance_confidence
    d["visual_match"] = params.visual_match
    d["preview_style"] = params.preview_style or {}
    d["appearance_pipeline"] = params.appearance_pipeline
    d["image_feature_summary"] = params.image_feature_summary
    d["vision_report_summary"] = params.vision_report_summary
    return d


def build_generic_rectangular_v2(p: dict[str, Any]) -> cq.Workplane:
    """Distinct from legacy MVP: twin crown ribs + lateral grooves."""
    length = p["body_length_mm"]
    width = p["body_width_mm"]
    height = p["body_height_mm"]
    er = min(1.2, width * 0.07, height * 0.07)
    body = cq.Workplane("XY").box(length, width, height).edges("|Z").fillet(er)
    rib = (
        cq.Workplane("XY")
        .box(length * 0.35, width * 0.22, height * 0.12)
        .translate((0, 0, height / 2 + height * 0.06))
    )
    body = body.union(rib)
    for sx in (-length * 0.22, length * 0.22):
        groove = (
            cq.Workplane("XY")
            .box(length * 0.12, width * 0.55, height * 0.35)
            .translate((sx, 0, 0))
        )
        body = body.cut(groove)
    front = cq.Workplane("XY").box(length * 0.55, width * 0.48, height * 0.38).translate((0, 0, height * 0.15))
    body = body.cut(front)
    for x, y in pin_cavity_positions(p):
        c = (
            cq.Workplane("XY")
            .circle(p["cavity_diameter_mm"] / 2)
            .extrude(height * 0.45)
            .translate((x, y, height / 2 - height * 0.2))
        )
        body = body.cut(c)
    return body


def build_te_blue_multi_cavity(p: dict[str, Any], layout: dict[str, Any] | None = None) -> cq.Workplane:
    """Multi-cavity grid face, top dual rails, side latch bosses, shroud lip."""
    length = p["body_length_mm"]
    width = p["body_width_mm"]
    height = p["body_height_mm"]
    layout = layout or {}
    cols = int(layout.get("grid_cols") or 3)
    rows = int(layout.get("grid_rows") or 2)
    active = int(layout.get("active_positions") or p.get("positions") or 2)

    base = cq.Workplane("XY").box(length, width, height)
    base = base.edges("|Z").fillet(min(1.4, width * 0.08))

    shroud_d = min(8.0, height * 0.38)
    shroud = (
        cq.Workplane("XY")
        .box(length * 0.92, width * 0.42, shroud_d)
        .translate((0, width * 0.23, height / 2 - shroud_d / 2 + 0.2))
    )
    model = base.union(shroud)

    pitch_x = length * 0.22
    pitch_y = width * 0.18
    cx0 = -((cols - 1) / 2) * pitch_x
    cy0 = -((rows - 1) / 2) * pitch_y + width * 0.05
    cd = p["cavity_diameter_mm"]
    cut_depth = min(height * 0.55, 14.0)
    slots = cols * rows
    n_cut = min(active, slots)
    for idx in range(n_cut):
        r = idx // cols
        c = idx % cols
        x = cx0 + c * pitch_x
        y = cy0 + r * pitch_y
        hole = cq.Workplane("XY").circle(cd / 2).extrude(cut_depth).translate((x, y, height / 2 - cut_depth + 0.1))
        model = model.cut(hole)

    rail_w = length * 0.38
    rail_h = min(2.8, height * 0.14)
    rail_d = width * 0.14
    for rx in (-length * 0.15, length * 0.15):
        rail = (
            cq.Workplane("XY")
            .box(rail_w * 0.45, rail_d, rail_h)
            .translate((rx, -width * 0.12, height / 2 + rail_h / 2 + 0.05))
        )
        model = model.union(rail)

    latch = (
        cq.Workplane("XY")
        .box(length * 0.12, width * 0.22, height * 0.25)
        .translate((length * 0.38, 0, height * 0.05))
    )
    model = model.union(latch)
    latch_l = (
        cq.Workplane("XY")
        .box(length * 0.12, width * 0.22, height * 0.25)
        .translate((-length * 0.38, 0, height * 0.05))
    )
    model = model.union(latch_l)

    return model


def build_te_superseal_2p(p: dict[str, Any]) -> cq.Workplane:
    """Two prominent front cavities + seal skirt + top latch tab."""
    length = max(p["body_length_mm"], 42.0)
    width = max(p["body_width_mm"], 20.0)
    height = max(p["body_height_mm"], 16.0)
    core = cq.Workplane("XY").box(length, width, height).edges("|Z").fillet(min(1.0, width * 0.06))
    skirt = (
        cq.Workplane("XY")
        .box(length * 1.05, width * 0.55, height * 0.2)
        .translate((0, -width * 0.12, -height / 2 + height * 0.08))
    )
    model = core.union(skirt)
    big_r = p["cavity_diameter_mm"] * 0.9
    for x in (-length * 0.16, length * 0.16):
        c = (
            cq.Workplane("XY")
            .circle(big_r / 2)
            .extrude(height * 0.5)
            .translate((x, 0, height / 2 - height * 0.28))
        )
        model = model.cut(c)
    latch = (
        cq.Workplane("XY")
        .box(length * 0.28, width * 0.35, 3.5)
        .translate((0, width / 2 + 1.4, height / 2 + 1.0))
    )
    model = model.union(latch)
    return model


def build_image_driven_proxy(p: dict[str, Any], features: dict[str, Any]) -> cq.Workplane:
    """Scale silhouette from image bbox; place holes from cavity candidates (approximate)."""
    sil = features.get("silhouette") or {}
    ar = float(sil.get("aspect_ratio") or 1.25)
    base_w = max(p["body_width_mm"], 18.0)
    length = max(p["body_length_mm"], base_w * ar)
    width = base_w
    height = max(p["body_height_mm"], 14.0)
    body = cq.Workplane("XY").box(length, width, height).edges("|Z").fillet(min(0.9, width * 0.07))

    cands = features.get("cavity_candidates") or []
    bb = features.get("bounding_box_px") or {}
    bw = float(bb.get("w") or 1)
    bh = float(bb.get("h") or 1)
    scale = max(length, width) / max(bw, bh, 1.0)
    cx0 = float(bb.get("x") or 0) + bw / 2
    cy0 = float(bb.get("y") or 0) + bh / 2
    hole_r = max(p["cavity_diameter_mm"] / 2, 1.2)
    for cand in cands[:12]:
        try:
            px = float(cand.get("cx", 0))
            py = float(cand.get("cy", 0))
        except (TypeError, ValueError):
            continue
        x = (px - cx0) * scale * 0.85
        y = (py - cy0) * scale * 0.85
        if abs(x) > length * 0.45 or abs(y) > width * 0.45:
            continue
        cut = cq.Workplane("XY").circle(hole_r).extrude(height * 0.45).translate((x, y, height / 2 - height * 0.2))
        body = body.cut(cut)
    if not cands:
        for x, y in pin_cavity_positions(p):
            cut = cq.Workplane("XY").circle(hole_r).extrude(height * 0.4).translate((x, y, height / 2 - height * 0.18))
            body = body.cut(cut)
    return body


def generate_series_template_cad(
    template_name: str,
    params: dict[str, Any],
    output_dir: str | Path,
    extra_layout: dict[str, Any] | None = None,
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    if template_name == "TE_BLUE_MULTI_CAVITY":
        model = build_te_blue_multi_cavity(params, extra_layout)
    elif template_name == "TE_SUPERSEAL_2P_STYLE":
        model = build_te_superseal_2p(params)
    elif template_name == "IMAGE_DRIVEN_PROXY":
        model = build_image_driven_proxy(params, extra_layout or {})
    else:
        model = build_generic_rectangular_v2(params)

    step_path = output_path / "model.step"
    stl_path = output_path / "model.stl"
    dxf_path = output_path / "drawing.dxf"
    exporters.export(model, str(step_path), exportType="STEP")
    exporters.export(model, str(stl_path), exportType="STL")
    write_engineering_dxf(params, dxf_path)
    return {"model.step": step_path, "model.stl": stl_path, "drawing.dxf": dxf_path}


def generate_image_approximated_cad(
    image_features: dict[str, Any],
    params: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    merged = dict(params)
    merged.setdefault("positions", 2)
    merged.setdefault("pitch_mm", 6.0)
    return generate_series_template_cad("IMAGE_DRIVEN_PROXY", merged, output_dir, extra_layout=image_features)


def export_appearance_job(params: ConnectorCadParams, output_dir: str | Path) -> dict[str, Path]:
    """Primary export for series_template / image_approximated / generic_mvp using appearance geometry."""
    output_path = Path(output_dir)
    normalized = _to_norm_dict(params)
    template = params.template_name or (params.appearance_pipeline or {}).get("template_name") or "GENERIC_RECTANGULAR_CONNECTOR"
    mode = params.model_origin
    layout: dict[str, Any] | None = None
    if template == "TE_BLUE_MULTI_CAVITY" and params.visual_match and params.visual_match.get("front_face_layout"):
        layout = params.visual_match.get("front_face_layout")  # type: ignore[assignment]
    if mode == "image_approximated" or template == "IMAGE_DRIVEN_PROXY":
        feats = params.image_feature_summary or {}
        files = generate_image_approximated_cad(feats, normalized, output_path)
    else:
        files = generate_series_template_cad(template, normalized, output_path, extra_layout=layout)

    params_path = output_path / "params.json"
    normalized_out = {
        **normalized,
        "template_name": template,
        "part_number": params.part_number or normalized.get("part_number"),
        "appearance_pipeline": params.appearance_pipeline,
        "appearance_confidence": params.appearance_confidence,
        "visual_match": params.visual_match,
        "preview_style": params.preview_style,
        "image_fallback_warning": params.image_fallback_warning,
    }
    write_params_json(params, normalized_out, params_path)
    files["params.json"] = params_path
    return files
