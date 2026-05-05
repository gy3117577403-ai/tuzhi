"""Orchestrate 2D flat CAD generation (classify → recipe → DXF/SVG → completeness)."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

from services.connector_2d_recipe import build_2d_connector_recipe
from services.connector_view_classifier import classify_connector_views
from services.flat_cad_generator import generate_flat_cad_views
from services.terminal_insertion_analyzer import analyze_terminal_insertion

FLAT_WARNINGS = [
    "Flat CAD views are visual/assembly aids, not official manufacturer drawings.",
]


def generate_flat_view_package(
    visual_recipe: dict[str, Any],
    image_features: dict[str, Any],
    vision_report: dict[str, Any],
    output_dir: str | Path,
    model_origin: str,
    user_hint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Returns dict with ok, flat_cad (for params.json), paths, error (optional).
    Does not raise on internal failures — callers embed status=failed in params.
    """
    output_dir = Path(output_dir)
    try:
        view_cls = classify_connector_views(image_features, vision_report, visual_recipe, user_hint)
        term = analyze_terminal_insertion(view_cls, visual_recipe, image_features, user_hint)
        recipe_2d = build_2d_connector_recipe(
            visual_recipe,
            image_features,
            view_cls,
            term,
            user_params=None,
            model_origin=model_origin,
        )
        gen = generate_flat_cad_views(recipe_2d, view_cls, term, output_dir)
        rep = gen["structure_report"]
        status = str(rep.get("status") or "partial")
        if status == "insufficient":
            status = "partial"

        flat_cad: dict[str, Any] = {
            "enabled": True,
            "status": status,
            "files": {
                "front_view_dxf": "connector_front_view.dxf",
                "rear_view_dxf": "connector_rear_view.dxf",
                "top_view_dxf": "connector_top_view.dxf",
                "side_view_dxf": "connector_side_view.dxf",
                "insertion_direction_dxf": "connector_insertion_direction.dxf",
                "flat_views_svg": "connector_flat_views.svg",
                "recipe": "connector_2d_recipe.json",
                "view_classification": "connector_view_classification.json",
                "terminal_insertion": "terminal_insertion.json",
                "structure_report": "structure_completeness_report.json",
            },
            "structure_completeness": {
                "status": rep.get("status"),
                "score": rep.get("score"),
            },
            "warnings": list(FLAT_WARNINGS) + list(rep.get("warnings") or []),
        }
        if rep.get("missing_items"):
            flat_cad["missing_items"] = rep["missing_items"]
        ti_sum = term.get("terminal_insertion") or {}
        flat_cad["terminal_insertion_summary"] = {
            "recommended_insertion_face": ti_sum.get("recommended_insertion_face"),
            "opposite_mating_face": ti_sum.get("opposite_mating_face"),
            "insertion_direction": ti_sum.get("insertion_direction"),
            "confidence": ti_sum.get("confidence"),
            "requires_manual_confirmation": ti_sum.get("requires_manual_confirmation"),
        }
        vcls = view_cls.get("view_classification") or {}
        flat_cad["view_classification_summary"] = {
            "input_image_view": vcls.get("input_image_view"),
            "mating_face_visible": vcls.get("mating_face_visible"),
            "wire_entry_face_visible": vcls.get("wire_entry_face_visible"),
            "terminal_insertion_face_likely": vcls.get("terminal_insertion_face_likely"),
            "orientation_confidence": vcls.get("orientation_confidence"),
        }

        return {
            "ok": True,
            "flat_cad": flat_cad,
            "paths": gen["paths"],
            "structure_report": rep,
            "error": None,
        }
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        tb = traceback.format_exc()
        return {
            "ok": False,
            "flat_cad": {
                "enabled": True,
                "status": "failed",
                "error": err,
                "error_trace": tb,
                "files": {},
                "structure_completeness": {"status": "insufficient", "score": 0.0},
                "warnings": FLAT_WARNINGS
                + [
                    "Flat CAD generation failed; 3D / other artifacts may still be available.",
                ],
            },
            "paths": {},
            "structure_report": None,
            "error": err,
        }
