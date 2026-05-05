"""Heuristic terminal insertion analysis — always tentative unless user confirms official data."""

from __future__ import annotations

from typing import Any


def analyze_terminal_insertion(
    view_classification: dict[str, Any],
    visual_recipe: dict[str, Any],
    image_features: dict[str, Any],
    user_hint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    user_hint = user_hint or {}
    vc = (view_classification or {}).get("view_classification") or {}
    likely_face = str(vc.get("terminal_insertion_face_likely") or "unknown")

    official_ok = bool(user_hint.get("official_datasheet_confirmed") or user_hint.get("physical_sample_confirmed"))
    requires_manual = not official_ok

    recommended = "rear_wire_entry_face"
    opposite = "front_mating_face"
    direction = "rear_to_front"
    view_wi = "rear_wire_entry_view"
    view_pin = "front_mating_face_view"
    confidence = "medium"

    if likely_face == "front_mating_face":
        recommended = "front_mating_face"
        opposite = "rear_wire_entry_face"
        direction = "front_to_rear"
        view_wi = "front_mating_face_view"
        view_pin = "rear_wire_entry_view"
        confidence = "low"
    elif likely_face == "unknown":
        confidence = "low"

    reasoning = [
        "Automotive-style housings often load terminals from the wire exit / rear side toward the mating cavity side.",
        "Front face in this recipe hosts the visible cavity grid typical of mating interface presentation.",
    ]
    if likely_face == "unknown":
        reasoning.append("Could not disambiguate insertion face from image alone — defaulting to common rear-to-front hypothesis.")

    if official_ok:
        reasoning.append("User indicated official datasheet or physical sample confirmation — lower automation risk, still document evidence.")

    return {
        "terminal_insertion": {
            "recommended_insertion_face": recommended,
            "opposite_mating_face": opposite,
            "insertion_direction": direction,
            "view_for_work_instruction": view_wi,
            "view_for_pin_check": view_pin,
            "confidence": confidence,
            "requires_manual_confirmation": requires_manual,
            "reasoning": reasoning,
        },
        "labels": {
            "front_mating_face": "對插正面 / 孔腔可見面",
            "rear_wire_entry_face": "入線面 / 端子插入面（推定）",
            "insertion_arrow": "端子由後向前插入（推定）" if direction == "rear_to_front" else "端子插入方向（推定）",
        },
        "warnings": [
            "Terminal insertion direction inferred; confirm with connector datasheet or physical sample.",
        ],
    }
