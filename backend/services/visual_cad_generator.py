"""Generate STEP/STL/DXF from visual shape grammar recipes (visual proxy only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cadquery as cq
from cadquery import exporters

from services.cad_generator import normalize_cad_params, write_params_json
from services.connector_params import PROVISIONAL_WARNING, ConnectorCadParams

VISUAL_PROXY_DISCLAIMER = (
    "Image-driven visual proxy CAD for appearance preview only. "
    "Not official manufacturer geometry; not manufacturing-grade."
)


def build_visual_proxy_geometry(recipe: dict[str, Any]) -> cq.Workplane:
    """Rich visual-proxy connector shell: split body, shroud lip + recess, cavity grid, rails, sides, rear."""
    dim = recipe.get("dimension_assumptions") or {}
    L = float(dim.get("length_mm", 28))
    W = float(dim.get("width_mm", 24))
    H = float(dim.get("height_mm", 22))

    # Primary rounded housing
    core = cq.Workplane("XY").box(L, W, H)
    core = core.edges("|Z").fillet(min(2.2, min(L, W) * 0.07))
    # Horizontal split-line groove (front vs rear personality)
    split_cut = cq.Workplane("XY").box(L * 0.96, W * 0.14, H * 0.26).translate((0, -W * 0.02, H * 0.06))
    model = core.cut(split_cut)

    cav = recipe.get("cavity_array") or {}
    rows = int(cav.get("rows") or 2)
    cols = int(cav.get("cols") or 3)
    active = int(cav.get("active_positions") or 4)
    cd = float(dim.get("cavity_diameter_mm", 4.2))
    depth = float(cav.get("recessed_depth_mm") or min(H * 0.52, 13.5))
    cav_shape = str(cav.get("cavity_shape") or "round")

    pitch_x = float(dim.get("pitch_along_cols_mm") or L / max(cols, 1) * 0.42)
    pitch_y = float(dim.get("pitch_along_rows_mm") or W / max(rows, 1) * 0.40)
    cx0 = -((cols - 1) / 2) * pitch_x
    cy0 = -((rows - 1) / 2) * pitch_y

    shroud = recipe.get("front_shroud") or {}
    if str(shroud.get("style") or "none") != "none":
        sd = float(shroud.get("lip_depth_mm") or min(9.0, H * 0.4))
        lip = (
            cq.Workplane("XY")
            .box(L * 0.93, W * 0.46, sd)
            .translate((0, W * 0.245, H / 2 - sd / 2 + 0.18))
        )
        model = model.union(lip)
        # Inner shroud pocket / frame opening
        pocket = (
            cq.Workplane("XY")
            .box(L * 0.58, W * 0.30, sd * 0.72)
            .translate((0, W * 0.20, H / 2 - sd * 0.42))
        )
        model = model.cut(pocket)

    n = 0
    for r in range(rows):
        for c in range(cols):
            if n >= active:
                break
            x = cx0 + c * pitch_x
            y = cy0 + r * pitch_y
            if cav_shape == "rounded_rect":
                slot = cq.Workplane("XY").rect(cd * 1.05, cd * 0.82).extrude(depth)
            else:
                slot = cq.Workplane("XY").circle(cd / 2).extrude(depth)
            slot = slot.translate((x, y, H / 2 - depth + 0.12))
            model = model.cut(slot)
            n += 1

    top = recipe.get("top_features") or {}
    if str(top.get("style")) == "dual_rails":
        rail_h = min(4.5, H * 0.19)
        rail_len = L * 0.36
        rail_w = W * 0.17
        for rx in (-L * 0.13, L * 0.13):
            rail = (
                cq.Workplane("XY")
                .box(rail_len, rail_w, rail_h)
                .translate((rx, -W * 0.105, H / 2 + rail_h / 2 + 0.08))
            )
            model = model.union(rail)

    side = recipe.get("side_features") or {}
    if side.get("grooves"):
        for gx in (L * 0.44, -L * 0.44):
            gcut = cq.Workplane("XY").box(L * 0.07, W * 0.38, H * 0.44).translate((gx, 0, H * 0.02))
            model = model.cut(gcut)
    if side.get("latch_blocks"):
        for sx in (L * 0.41, -L * 0.41):
            latch = (
                cq.Workplane("XY")
                .box(L * 0.13, W * 0.24, H * 0.28)
                .translate((sx, W * 0.05, H * 0.02))
            )
            model = model.union(latch)

    bottom = recipe.get("bottom_features") or {}
    if str(bottom.get("style")) == "step":
        ledge = cq.Workplane("XY").box(L * 0.9, W * 0.22, H * 0.09).translate((0, -W * 0.06, -H / 2 + H * 0.065))
        model = model.union(ledge)

    rear = recipe.get("rear_features") or {}
    if str(rear.get("style")) == "wire_exit":
        cut = cq.Workplane("XY").box(L * 0.4, W * 0.32, H * 0.22).translate((0, -W * 0.36, -H * 0.28))
        model = model.cut(cut)

    return model


def generate_visual_proxy_cad(recipe: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    model = build_visual_proxy_geometry(recipe)
    step_path = output_path / "model.step"
    stl_path = output_path / "model.stl"
    dxf_path = output_path / "drawing.dxf"
    exporters.export(model, str(step_path), exportType="STEP")
    exporters.export(model, str(stl_path), exportType="STL")
    minimal = _minimal_dxf_stub()
    dxf_path.write_text(minimal, encoding="utf-8")
    (output_path / "visual_recipe.json").write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"model.step": step_path, "model.stl": stl_path, "drawing.dxf": dxf_path}


def _minimal_dxf_stub() -> str:
    return "\n".join(["0", "SECTION", "2", "ENTITIES", "0", "ENDSEC", "0", "EOF", ""])


def export_visual_proxy_job(params: ConnectorCadParams, output_dir: str | Path) -> dict[str, Path]:
    """Export appearance files + params.json for visual-grammar jobs."""
    recipe = getattr(params, "visual_recipe", None) or {}
    if not recipe:
        raise ValueError("visual_recipe missing on params for visual proxy export")

    files = generate_visual_proxy_cad(recipe, output_dir)
    normalized = normalize_cad_params(params)
    normalized["visual_recipe"] = recipe
    normalized["geometry_basis"] = params.geometry_basis or "visual_shape_grammar"
    normalized["manufacturing_accuracy"] = params.manufacturing_accuracy or "visual_proxy_only"
    normalized["model_origin"] = params.model_origin
    normalized["preview_style"] = params.preview_style or {"base_color": recipe.get("color", "grey")}
    normalized["appearance_pipeline"] = params.appearance_pipeline
    normalized["image_feature_summary"] = params.image_feature_summary
    normalized["vision_report_summary"] = params.vision_report_summary
    normalized["uploaded_file_name"] = params.uploaded_file_name
    normalized["image_search_context"] = params.image_search_context
    normalized["image_search"] = params.image_search
    normalized["disclaimer"] = VISUAL_PROXY_DISCLAIMER
    normalized["warning"] = params.warning or PROVISIONAL_WARNING

    params_path = Path(output_dir) / "params.json"
    write_params_json(params, normalized, params_path)
    files["params.json"] = params_path
    return files
