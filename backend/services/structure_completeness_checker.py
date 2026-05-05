"""Score structural completeness of generated 2D flat CAD outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

REQUIRED_FILES = (
    "connector_front_view.dxf",
    "connector_rear_view.dxf",
    "connector_top_view.dxf",
    "connector_side_view.dxf",
    "connector_insertion_direction.dxf",
    "connector_flat_views.svg",
)


def check_structure_completeness(recipe: dict[str, Any], generated_files: dict[str, Path]) -> dict[str, Any]:
    by_name = {p.name: p for p in generated_files.values() if isinstance(p, Path)}
    views = recipe.get("views") or {}
    front = views.get("front_mating_face") or {}
    rear = views.get("rear_wire_entry_face") or {}
    cav = front.get("cavity_array") or {}
    ti = recipe.get("terminal_insertion") or {}

    checks = {
        "front_view_exists": by_name.get("connector_front_view.dxf", Path()).exists(),
        "rear_view_exists": by_name.get("connector_rear_view.dxf", Path()).exists(),
        "top_view_exists": by_name.get("connector_top_view.dxf", Path()).exists(),
        "side_view_exists": by_name.get("connector_side_view.dxf", Path()).exists(),
        "cavity_array_present": bool(cav.get("rows") and cav.get("cols")),
        "cavity_numbering_present": bool(cav.get("active_positions")),
        "terminal_insertion_direction_present": bool(
            by_name.get("connector_insertion_direction.dxf", Path()).exists() and ti.get("insertion_direction")
        ),
        "front_rear_labels_present": bool(front.get("title") and rear.get("title")),
        "warnings_present": bool(recipe.get("warnings")),
    }

    json_ok = all(
        (by_name.get(n, Path()).exists())
        for n in (
            "connector_2d_recipe.json",
            "connector_view_classification.json",
            "terminal_insertion.json",
        )
    )
    checks["companion_json_present"] = json_ok

    missing: list[str] = []
    for fn in REQUIRED_FILES:
        p = by_name.get(fn)
        if not p or not p.exists():
            missing.append(fn)

    # recipe JSON etc. checked separately
    for fn in ("connector_2d_recipe.json", "connector_view_classification.json", "terminal_insertion.json"):
        p = by_name.get(fn)
        if not p or not p.exists():
            missing.append(fn)

    weights = list(checks.values())
    score = round(sum(1 for v in weights if v) / max(len(weights), 1), 3)

    core_ok = checks["front_view_exists"] and checks["rear_view_exists"] and checks["terminal_insertion_direction_present"]
    if not core_ok:
        status = "insufficient"
    elif missing:
        status = "partial"
    elif checks["warnings_present"] and score >= 0.85:
        status = "complete"
    elif score >= 0.75:
        status = "complete"
    else:
        status = "partial"

    warn = [
        "Dimensions are assumed and require confirmation.",
        "Flat CAD views are visual / SOP aids, not official manufacturer drawings.",
    ]

    return {
        "status": status,
        "score": score,
        "checks": checks,
        "missing_items": missing,
        "warnings": warn,
    }
