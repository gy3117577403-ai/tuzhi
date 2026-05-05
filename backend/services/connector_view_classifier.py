"""Infer connector face / view orientation from image features (non-definitive)."""

from __future__ import annotations

from typing import Any


def classify_connector_views(
    image_features: dict[str, Any],
    vision_report: dict[str, Any] | None,
    visual_recipe: dict[str, Any],
    user_hint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    vision_report = vision_report or {}
    user_hint = user_hint or {}
    ff = image_features.get("feature_flags") or {}
    view_angle = str(image_features.get("view_angle") or "unknown")
    layout = image_features.get("front_face_layout") or visual_recipe.get("cavity_array") or {}

    multi = bool(ff.get("multi_cavity"))
    shroud = bool(ff.get("front_shroud"))
    has_cavity_signal = multi or shroud or int(layout.get("active_positions") or 0) > 1
    wire_exit = bool(ff.get("wire_exit_rear") or ff.get("wire_exit"))
    rear_recipe = (visual_recipe.get("rear_features") or {}).get("style") == "wire_exit"

    mating_face_visible = bool(
        has_cavity_signal
        or image_features.get("front_face_visible")
        or image_features.get("front_face_likely")
    )
    wire_entry_face_visible = bool(wire_exit or rear_recipe)

    if view_angle == "top-front":
        input_image_view = "top_front"
    elif view_angle == "side-front":
        input_image_view = "side_front"
    elif has_cavity_signal and not wire_exit:
        input_image_view = "front_mating_face"
    elif wire_exit and not has_cavity_signal:
        input_image_view = "rear_wire_entry"
    elif has_cavity_signal and wire_exit:
        input_image_view = "front_mating_face"
    else:
        input_image_view = "unknown"

    if has_cavity_signal:
        terminal_likely = "rear_wire_entry"
    elif wire_exit:
        terminal_likely = "front_mating_face"
    else:
        terminal_likely = "unknown"

    orient_conf = str(image_features.get("confidence") or "medium")
    if input_image_view == "unknown":
        orient_conf = "low"

    reasoning: list[str] = []
    if has_cavity_signal:
        reasoning.append("Cavity grid / shroud / multi-cavity cues suggest mating face visible in image.")
    if wire_exit or rear_recipe:
        reasoning.append("Wire-exit / rear-opening cues suggest rear wire-entry region.")
    if view_angle in ("top-front", "side-front"):
        reasoning.append(f"Estimated camera angle: {view_angle} — orthographic views are synthesized, not photographed.")
    if user_hint.get("note"):
        reasoning.append(f"User hint noted: {user_hint.get('note')}")

    faces = {
        "front_mating_face": {
            "available": True,
            "confidence": "medium" if mating_face_visible else "low",
            "basis": "cavity array and/or front shroud in recipe / features"
            if has_cavity_signal
            else "provisional front synthesized for documentation",
        },
        "rear_wire_entry_face": {
            "available": True,
            "confidence": "low" if wire_entry_face_visible else "low",
            "basis": "inferred rear wire exit / recipe rear_features"
            if (wire_exit or rear_recipe)
            else "provisional rear synthesized (limited rear cues)",
        },
        "top_view": {
            "available": True,
            "confidence": "medium" if view_angle == "top-front" else "low",
            "basis": "derived schematic top from housing depth / rails recipe",
        },
        "side_view": {
            "available": True,
            "confidence": "medium" if view_angle == "side-front" else "medium",
            "basis": "derived schematic side (grooves / steps from recipe)",
        },
    }

    warnings = [
        "View classification is inferred from image; verify before production use.",
        "This is not an official manufacturer drawing.",
    ]

    return {
        "view_classification": {
            "input_image_view": input_image_view,
            "mating_face_visible": bool(mating_face_visible),
            "wire_entry_face_visible": bool(wire_entry_face_visible),
            "terminal_insertion_face_likely": terminal_likely,
            "orientation_confidence": orient_conf,
            "reasoning": reasoning or ["Limited cues — using provisional orthogonal set."],
        },
        "faces": faces,
        "warnings": warnings,
    }
