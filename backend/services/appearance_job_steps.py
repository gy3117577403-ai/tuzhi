from __future__ import annotations

from pathlib import Path
from typing import Any

from services.ai_param_extractor import extract_connector_params_with_ai_detailed
from services.connector_params import (
    ConnectorCadParams,
    apply_visual_registry_item,
)
from services.part_visual_registry import find_visual_item
from services.series_template_selector import select_template


def _ai_skipped() -> dict[str, Any]:
    from services.ai_param_extractor import DEFAULT_EXTRACTED
    from services.ai_client import get_ai_env

    env = get_ai_env()
    return {
        "enabled": False,
        "status": "skipped",
        "provider": env.get("provider", "openai_compatible"),
        "model": env.get("model", "") or "",
        "error": "",
        "extracted": {**DEFAULT_EXTRACTED},
    }


def configure_text_appearance_pipeline(params: ConnectorCadParams, text: str) -> ConnectorCadParams:
    """Visual registry + AI + template selection for text jobs (non-official)."""
    extracted, ai_block = extract_connector_params_with_ai_detailed(text.strip())
    from services.connector_params import merge_ai_extracted_into_params

    next_p = merge_ai_extracted_into_params(params, extracted, ai_block)

    visual_item = find_visual_item(text=text)
    if visual_item:
        next_p = apply_visual_registry_item(next_p, visual_item)

    try:
        pos_hint = int(next_p.dimensions["pin_count"].value)
    except (KeyError, TypeError, ValueError):
        pos_hint = None

    sel = select_template(
        visual_registry_item=visual_item,
        ai_extracted=extracted,
        user_text=text,
        positions_hint=pos_hint,
    )

    if visual_item:
        origin = "series_template"
    elif sel.template_name == "GENERIC_RECTANGULAR_CONNECTOR":
        origin = "generic_mvp"
    else:
        origin = "series_template"

    preview = next_p.preview_style or {}
    if sel.color:
        preview = {**preview, "base_color": sel.color}

    pipeline = {
        "used": True,
        "mode": origin,
        "template_name": sel.template_name,
        "selection_reason": sel.selection_reason,
        "preview_color": preview.get("base_color") or sel.color,
        "image_features_file": None,
        "vision_report_file": None,
    }

    next_p = next_p.model_copy(
        update={
            "model_origin": origin,  # type: ignore[arg-type]
            "template_name": sel.template_name,
            "appearance_confidence": sel.confidence,
            "preview_style": preview,
            "appearance_pipeline": pipeline,
            "selection_reason": sel.selection_reason,
        }
    )
    if not visual_item and not next_p.visual_match:
        next_p.visual_match = {
            "matched_from_registry": False,
            "registry_item_id": None,
            "selection_reason": sel.selection_reason,
        }
    return next_p


from services.search_to_cad_pipeline import build_params_from_uploaded_image


def configure_image_appearance_pipeline(
    params: ConnectorCadParams,
    output_dir: Path,
    filename: str | None,
    text: str | None,
) -> ConnectorCadParams:
    """Upload / photo: visual grammar CAD (image_upload_approximated) or generic fallback."""
    return build_params_from_uploaded_image(params, output_dir, filename, text)


def is_image_upload(filename: str | None) -> bool:
    if not filename:
        return False
    return Path(filename).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
