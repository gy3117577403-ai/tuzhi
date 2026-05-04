from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.ai_param_extractor import extract_connector_params_with_ai_detailed
from services.connector_params import (
    ConnectorCadParams,
    apply_visual_registry_item,
)
from services.image_feature_extractor import extract_image_features, summarize_features_for_storage
from services.part_visual_registry import find_visual_item
from services.series_template_selector import select_template
from services.vision_ai_extractor import extract_vision_analysis


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


def configure_image_appearance_pipeline(
    params: ConnectorCadParams,
    output_dir: Path,
    filename: str | None,
    text: str | None,
) -> ConnectorCadParams:
    """Image features + vision AI + image-approx or generic fallback."""
    if not filename:
        return params.model_copy(
            update={
                "model_origin": "generic_mvp",  # type: ignore[arg-type]
                "template_name": "GENERIC_RECTANGULAR_CONNECTOR",
                "appearance_pipeline": {
                    "used": True,
                    "mode": "generic_mvp",
                    "template_name": "GENERIC_RECTANGULAR_CONNECTOR",
                    "selection_reason": "No upload file present.",
                    "preview_color": "grey",
                    "image_features_file": None,
                    "vision_report_file": None,
                },
                "ai_extraction": _ai_skipped(),
            }
        )

    src = output_dir / f"source_{filename}"
    if not src.exists():
        return params.model_copy(
            update={
                "model_origin": "generic_mvp",  # type: ignore[arg-type]
                "template_name": "GENERIC_RECTANGULAR_CONNECTOR",
                "ai_extraction": _ai_skipped(),
                "appearance_pipeline": {
                    "used": True,
                    "mode": "generic_mvp",
                    "template_name": "GENERIC_RECTANGULAR_CONNECTOR",
                    "selection_reason": "Upload file missing on disk; generic template fallback.",
                    "preview_color": "grey",
                    "image_features_file": None,
                    "vision_report_file": None,
                },
                "preview_style": {"base_color": "grey"},
            }
        )

    feats = extract_image_features(src)
    (output_dir / "image_features.json").write_text(json.dumps(feats, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = summarize_features_for_storage(feats)
    vision = extract_vision_analysis(src, text, summary)
    (output_dir / "vision_report.json").write_text(json.dumps(vision, ensure_ascii=False, indent=2), encoding="utf-8")

    cands = feats.get("cavity_candidates") or []
    rect = float((feats.get("silhouette") or {}).get("rectangularity") or 0)
    sufficient = len(cands) >= 2 or rect >= 0.48

    preview_color = vision.get("likely_color") or feats.get("dominant_color") or "grey"

    if sufficient:
        origin = "image_approximated"
        template = "IMAGE_DRIVEN_PROXY"
        reason = "Sufficient cavity / silhouette cues from image features for appearance proxy."
        fb = None
    else:
        origin = "generic_mvp"
        template = "GENERIC_RECTANGULAR_CONNECTOR"
        reason = "Image features insufficient for confident silhouette proxy; fell back to upgraded generic template."
        fb = "图片特征不足，已回退至通用参数化白模（升级版外形）。形态预览仅供参考。"

    pipeline = {
        "used": True,
        "mode": origin,
        "template_name": template,
        "selection_reason": reason,
        "preview_color": preview_color,
        "image_features_file": "image_features.json",
        "vision_report_file": "vision_report.json",
    }

    return params.model_copy(
        update={
            "model_origin": origin,  # type: ignore[arg-type]
            "template_name": template,
            "appearance_confidence": str(vision.get("confidence") or "low"),
            "preview_style": {"base_color": preview_color},
            "appearance_pipeline": pipeline,
            "image_feature_summary": feats,
            "vision_report_summary": vision,
            "image_fallback_warning": fb,
            "visual_match": {
                "matched_from_registry": False,
                "registry_item_id": None,
                "selection_reason": reason,
            },
            "ai_extraction": _ai_skipped(),
        }
    )


def is_image_upload(filename: str | None) -> bool:
    if not filename:
        return False
    return Path(filename).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
