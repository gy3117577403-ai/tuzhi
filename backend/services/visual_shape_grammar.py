"""Visual shape grammar: compose CAD primitives from extracted vision features (no per-part-number templates)."""

from __future__ import annotations

from typing import Any


def build_shape_recipe_from_visual_features(
    features: dict[str, Any],
    ai_report: dict[str, Any] | None = None,
    user_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a neutral structural recipe for CadQuery assembly.

    recipe_type is always visual_proxy_connector — geometry_basis handled at export.
    """
    ai_report = ai_report or {}
    user_params = user_params or {}

    dom_color = str(features.get("dominant_color") or ai_report.get("likely_color") or "grey")
    body_shape = str(features.get("body_shape") or "rectangular_housing")

    ff = features.get("feature_flags") or {}
    layout = features.get("front_face_layout") or {}
    rows = int(layout.get("grid_rows") or 2)
    cols = int(layout.get("grid_cols") or 3)
    active = int(layout.get("active_positions") or max(1, min(rows * cols, 6)))

    top_rails = bool(ff.get("top_rails") or ff.get("top_dual_rails"))
    front_shroud_flag = bool(ff.get("front_shroud"))
    multi_cavity = bool(ff.get("multi_cavity")) or active > 1
    side_latches = bool(
        ff.get("side_latches") or ff.get("side_latch_like") or ff.get("side_latches_possible")
    )

    # Rules: shroud + cavity front whenever cues say multi / shroud (non-mm-dependent).
    need_shroud = front_shroud_flag or multi_cavity
    if multi_cavity and active < 4 and rows * cols < 6:
        rows, cols, active = 2, 3, min(6, max(active, 4))

    base_style = "rounded_rectangular" if body_shape in ("rounded_rectangular", "rectangular_housing") else "rectangular"

    fr_shroud_style = "none"
    if need_shroud:
        fr_shroud_style = "deep_frame" if multi_cavity else "shallow_frame"

    dim = _default_dimensions_from_features(features, active, rows, cols)

    warnings = list(features.get("warnings") or [])
    warnings.append("Visual-proxy geometry is not manufacturing-grade; confirm all dimensions manually.")

    cav_shape = "rounded_rect"
    if not multi_cavity:
        cav_shape = "round"

    recipe: dict[str, Any] = {
        "recipe_type": "visual_proxy_connector",
        "base_body": {"style": base_style, "outline": body_shape, "split_body_segments": 2},
        "front_shroud": {"style": fr_shroud_style, "lip_depth_mm": round(dim["height_mm"] * 0.35, 2)},
        "cavity_array": {
            "rows": rows,
            "cols": cols,
            "active_positions": active,
            "cavity_shape": cav_shape,
            "recessed_depth_mm": round(min(dim["height_mm"] * 0.5, 14.0), 2),
        },
        "top_features": {"style": "dual_rails" if (top_rails or multi_cavity) else "flat"},
        "side_features": {
            "latch_blocks": side_latches,
            "grooves": bool(multi_cavity or side_latches),
            "guide_tabs": bool(multi_cavity),
        },
        "bottom_features": {"style": "step" if (side_latches or multi_cavity) else "flat"},
        "rear_features": {"style": "wire_exit"},
        "color": dom_color,
        "dimension_assumptions": dim,
        "confidence": str(features.get("confidence") or "medium"),
        "warnings": warnings,
        "view_angle": str(features.get("view_angle") or "unknown"),
    }
    return recipe


def _default_dimensions_from_features(features: dict[str, Any], active: int, rows: int, cols: int) -> dict[str, float]:
    sil = features.get("silhouette") or {}
    ar = float(sil.get("aspect_ratio") or 1.2)
    base_w = 22.0
    length = max(24.0, min(52.0, base_w * max(1.0, ar)))
    width = max(18.0, min(44.0, base_w))
    height = max(14.0, min(30.0, width * 0.85))

    pitch_est = max(5.5, min(length / max(cols, 1), 12.0))
    cav_d = max(2.8, min(pitch_est * 0.72, 8.0))

    return {
        "length_mm": round(length, 2),
        "width_mm": round(width, 2),
        "height_mm": round(height, 2),
        "cavity_diameter_mm": round(cav_d, 2),
        "pitch_along_rows_mm": round(pitch_est, 2),
        "pitch_along_cols_mm": round(pitch_est * 0.92, 2),
        "reference_positions": float(active),
        "layout_rows": float(rows),
        "layout_cols": float(cols),
    }
