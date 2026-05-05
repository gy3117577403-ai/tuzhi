"""Build a 2D flat-view recipe (schematic, non-manufacturing-grade dimensions)."""

from __future__ import annotations

from typing import Any


def build_2d_connector_recipe(
    visual_recipe: dict[str, Any],
    image_features: dict[str, Any],
    view_classification: dict[str, Any],
    terminal_insertion: dict[str, Any],
    user_params: dict[str, Any] | None = None,
    model_origin: str = "image_search_approximated",
) -> dict[str, Any]:
    user_params = user_params or {}
    dim_v = visual_recipe.get("dimension_assumptions") or {}
    cav = visual_recipe.get("cavity_array") or {}
    rows = int(cav.get("rows") or 2)
    cols = int(cav.get("cols") or 3)
    active = int(cav.get("active_positions") or rows * cols)
    cav_shape = str(cav.get("cavity_shape") or "rounded_rect")

    body_w = float(dim_v.get("width_mm") or 24)
    body_h = float(dim_v.get("height_mm") or 22)
    body_d = float(dim_v.get("length_mm") or 28)
    pitch_x = float(dim_v.get("pitch_along_cols_mm") or max(5.5, body_w / max(cols, 1)))
    pitch_y = float(dim_v.get("pitch_along_rows_mm") or max(5.5, body_h / max(rows, 1)))
    cdi = float(dim_v.get("cavity_diameter_mm") or 4.2)
    cw = round(cdi * 1.05, 2)
    ch = round(cdi * 0.82, 2)

    warnings = list(view_classification.get("warnings") or [])
    warnings.extend(list(terminal_insertion.get("warnings") or []))
    warnings.append("All dimensions are assumed for schematic documentation — not metrology-grade.")
    if visual_recipe.get("warnings"):
        warnings.extend(str(x) for x in (visual_recipe.get("warnings") or [])[:3])

    top_style = str((visual_recipe.get("top_features") or {}).get("style") or "flat")
    side = visual_recipe.get("side_features") or {}

    recipe: dict[str, Any] = {
        "recipe_type": "connector_2d_flat_views",
        "model_origin": model_origin,
        "units": "mm",
        "scale_basis": user_params.get("scale_basis") or "assumed",
        "dimension_assumptions": {
            "body_width_mm": round(body_w, 2),
            "body_height_mm": round(body_h, 2),
            "body_depth_mm": round(body_d, 2),
            "cavity_pitch_x_mm": round(pitch_x, 2),
            "cavity_pitch_y_mm": round(pitch_y, 2),
            "cavity_width_mm": cw,
            "cavity_height_mm": ch,
        },
        "views": {
            "front_mating_face": {
                "enabled": True,
                "title": "正面 / 對插面（示意）",
                "cavity_array": {
                    "rows": rows,
                    "cols": cols,
                    "active_positions": active,
                    "cavity_shape": cav_shape,
                    "numbering": "left_to_right_top_to_bottom",
                },
                "features": [
                    "front_shroud" if (visual_recipe.get("front_shroud") or {}).get("style") not in (None, "none") else "housing_face",
                    "cavity_grid",
                    "guide_slots" if side.get("guide_tabs") else "outline",
                ],
            },
            "rear_wire_entry_face": {
                "enabled": True,
                "title": "反面 / 入線面 / 端子插入面（示意）",
                "terminal_entry_array": {
                    "rows": rows,
                    "cols": cols,
                    "entry_shape": "rounded_rect",
                },
                "features": ["wire_entry", "terminal_insertion_arrows"],
            },
            "top_view": {
                "enabled": True,
                "features": [
                    "dual_rails" if top_style == "dual_rails" else "shell_outline",
                    "latch_area",
                    "front_rear_depth",
                ],
            },
            "side_view": {
                "enabled": True,
                "features": [
                    "side_grooves" if side.get("grooves") else "side_outline",
                    "guide_tabs" if side.get("guide_tabs") else "outline",
                    "body_steps" if (visual_recipe.get("bottom_features") or {}).get("style") == "step" else "profile",
                ],
            },
        },
        "terminal_insertion": terminal_insertion.get("terminal_insertion"),
        "view_classification": view_classification.get("view_classification"),
        "labels": terminal_insertion.get("labels"),
        "warnings": warnings,
    }
    return recipe
