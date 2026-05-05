"""Orchestrate image search → rank → download → vision features → visual CAD."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from services.connector_params import ConnectorCadParams, DimensionValue, PROVISIONAL_WARNING
from services.image_download import download_image_to_job
from services.image_feature_extractor import extract_image_features, summarize_features_for_storage
from services.image_search_client import search_connector_images
from services.search_result_ranker import rank_connector_image_results
from services.vision_ai_extractor import extract_vision_analysis
from services.visual_shape_grammar import build_shape_recipe_from_visual_features


def _disclaimer_visual_search() -> str:
    return (
        "该模型由搜索图片自动生成，仅为外观近似 CAD，不代表原厂精确几何或制造级尺寸。"
        " 关键尺寸必须人工确认后方可用于生产。"
    )


def _disclaimer_upload() -> str:
    return (
        "该模型依据上传图像的视觉近似生成，仅为外观参考，非原厂精确 CAD；制造前须人工确认关键尺寸。"
    )


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


def download_reference_image(url: str, dest: Path, timeout_sec: float = 45.0) -> bool:
    try:
        with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
        return dest.exists() and dest.stat().st_size > 32
    except Exception:
        return False


def _apply_recipe_dimensions(base: ConnectorCadParams, recipe: dict[str, Any]) -> ConnectorCadParams:
    d = recipe.get("dimension_assumptions") or {}
    np = base.model_copy(deep=True)
    try:
        if "length_mm" in d:
            np.dimensions["overall_length"] = DimensionValue(
                value=float(d["length_mm"]), source="default_mvp", confidence="medium"
            )
        if "width_mm" in d:
            np.dimensions["overall_width"] = DimensionValue(
                value=float(d["width_mm"]), source="default_mvp", confidence="medium"
            )
        if "height_mm" in d:
            np.dimensions["overall_height"] = DimensionValue(
                value=float(d["height_mm"]), source="default_mvp", confidence="medium"
            )
        cav = recipe.get("cavity_array") or {}
        active = int(cav.get("active_positions") or 2)
        np.dimensions["pin_count"] = DimensionValue(value=active, unit="count", source="default_mvp", confidence="medium")
        if "cavity_diameter_mm" in d:
            cd = float(d["cavity_diameter_mm"])
            np.dimensions["pin_diameter"] = DimensionValue(
                value=round(cd / 1.6, 4), source="default_mvp", confidence="medium"
            )
        if "pitch_along_cols_mm" in d:
            np.dimensions["pin_pitch"] = DimensionValue(
                value=float(d["pitch_along_cols_mm"]), source="default_mvp", confidence="medium"
            )
    except Exception:
        pass
    return np


def generate_cad_from_search(
    query: str,
    output_dir: Path,
    base_params: ConnectorCadParams,
    selected_image_url: str | None = None,
    selected_image: dict[str, Any] | None = None,
    search_pack_override: dict[str, Any] | None = None,
) -> tuple[ConnectorCadParams | None, dict[str, Any]]:
    """
    Full pipeline: search → rank → download → features → recipe-ready params.

    Returns (params, meta). params is None → caller should fall back to registry / AI / generic.
    """
    meta: dict[str, Any] = {"image_search": {}}

    img_path = output_dir / "reference_selected.png"
    search_pack: dict[str, Any] = {}

    if selected_image_url:
        search_pack = search_pack_override or {
            "query": query,
            "provider": "manual_url",
            "status": "manual",
            "results": [],
            "warnings": [],
        }
        (output_dir / "image_search_results.json").write_text(
            json.dumps(search_pack, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        dl = download_image_to_job(selected_image_url.strip(), output_dir, "reference_selected")
        if not dl.get("ok"):
            meta["error"] = dl.get("error") or "Failed to download selected_image_url"
            return None, meta
        img_path = Path(dl["saved_path"])
        selected = selected_image or {
            "title": "user_selected",
            "image_url": selected_image_url.strip(),
            "thumbnail_url": selected_image_url.strip(),
            "source_url": selected_image_url.strip(),
            "domain": "",
            "rank": 1,
        }
        rank_summary = {
            "selected": selected,
            "candidates": [selected],
            "selection_reason": "User supplied reference image URL.",
            "confidence": "high",
            "needs_user_selection": False,
        }
        (output_dir / "selected_image.json").write_text(
            json.dumps({"selected": selected, "rank_summary": rank_summary, "download": dl}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        search_pack = search_connector_images(query)
        (output_dir / "image_search_results.json").write_text(
            json.dumps(search_pack, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        meta["image_search"] = {"status": search_pack.get("status"), "provider": search_pack.get("provider")}

        if search_pack.get("status") == "not_configured":
            return None, meta

        if search_pack.get("status") != "success" or not search_pack.get("results"):
            meta["image_search"]["failure"] = search_pack.get("warnings") or ["no results"]
            return None, meta

        ranked = rank_connector_image_results(query, search_pack.get("results") or [])
        sel = ranked.get("selected")
        if not sel or not sel.get("image_url"):
            return None, {**meta, "rank": ranked}

        img_url = str(sel.get("image_url") or "").strip()
        dl = download_image_to_job(img_url, output_dir, "reference_selected")
        if not dl.get("ok"):
            return None, {**meta, "error": dl.get("error") or "download_failed", "rank": ranked}
        img_path = Path(dl["saved_path"])

        (output_dir / "selected_image.json").write_text(
            json.dumps({"selected": sel, "rank_summary": ranked, "download": dl}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rank_summary = ranked
        selected = sel

    feats = extract_image_features(img_path)
    (output_dir / "image_features.json").write_text(
        json.dumps(feats, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = {
        "dominant_color": feats.get("dominant_color"),
        "front_face_layout": feats.get("front_face_layout"),
        "feature_flags": feats.get("feature_flags"),
        "view_angle": feats.get("view_angle"),
        "confidence": feats.get("confidence"),
        "warnings": feats.get("warnings"),
    }
    vision = extract_vision_analysis(img_path, query, summary)
    (output_dir / "vision_report.json").write_text(json.dumps(vision, ensure_ascii=False, indent=2), encoding="utf-8")

    recipe = build_shape_recipe_from_visual_features(feats, vision, {})
    (output_dir / "visual_recipe.json").write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding="utf-8")

    np = _apply_recipe_dimensions(base_params, recipe)
    np = np.model_copy(
        update={
            "title": (query or "")[:80] or np.title,
            "part_number": (query or "")[:80] or np.part_number,
            "model_origin": "image_search_approximated",
            "template_name": "VISUAL_GRAMMAR_PROXY",
            "appearance_confidence": str(recipe.get("confidence") or "medium"),
            "preview_style": {"base_color": recipe.get("color") or "grey"},
            "geometry_basis": "visual_shape_grammar",
            "manufacturing_accuracy": "visual_proxy_only",
            "visual_recipe": recipe,
            "image_feature_summary": feats,
            "vision_report_summary": vision,
            "image_search_context": {
                "search": search_pack,
                "rank": rank_summary,
                "reference_image_file": img_path.name,
            },
            "image_search": {
                "query": query,
                "provider": search_pack.get("provider"),
                "status": search_pack.get("status"),
                "selected": selected,
                "reference_image_file": img_path.name,
                "results_file": "image_search_results.json",
                "selected_image_file": "selected_image.json",
            },
            "appearance_pipeline": {
                "used": True,
                "mode": "image_search_approximated",
                "template_name": "VISUAL_GRAMMAR_PROXY",
                "selection_reason": rank_summary.get("selection_reason", ""),
                "preview_color": recipe.get("color"),
                "image_features_file": "image_features.json",
                "vision_report_file": "vision_report.json",
                "visual_recipe_file": "visual_recipe.json",
                "image_search_results_file": "image_search_results.json",
                "selected_image_file": "selected_image.json",
            },
            "visual_match": {
                "matched_from_registry": False,
                "selection_reason": "Image search + visual grammar (not part-number template library).",
            },
            "disclaimer": _disclaimer_visual_search(),
            "warning": PROVISIONAL_WARNING + " " + _disclaimer_visual_search(),
            "source_url": str((rank_summary.get("selected") or {}).get("source_url") or selected_image_url or ""),
            "ai_extraction": _ai_skipped(),
            "notes": "Dimensions derived from visual proxy assumptions — confirm before manufacturing.",
        }
    )

    meta["ok"] = True
    meta["rank"] = rank_summary
    meta.setdefault("image_search", {}).update(
        {"status": search_pack.get("status"), "provider": search_pack.get("provider")}
        if search_pack
        else {}
    )
    return np, meta


def _upload_should_fallback_generic(feats: dict[str, Any], img_w: int, img_h: int) -> tuple[bool, str]:
    """Only skip visual grammar when there is essentially no connector-like signal."""
    ff = feats.get("feature_flags") or {}
    bbox = feats.get("bounding_box_px") or {}
    area_r = (bbox.get("w", 0) * bbox.get("h", 0)) / max(img_w * img_h, 1)
    sil = feats.get("silhouette") or {}
    rect = float(sil.get("rectangularity") or 0)
    n_circ = len(feats.get("cavity_candidates") or [])
    dom = feats.get("dominant_color") or "grey"
    blue_frac = float(feats.get("blue_fraction_estimate") or 0)

    any_structural = any(
        [
            ff.get("multi_cavity"),
            ff.get("front_shroud"),
            ff.get("top_rails"),
            ff.get("top_dual_rails"),
            ff.get("side_latches"),
            ff.get("side_latches_possible"),
            ff.get("side_latch_like"),
            n_circ >= 1,
            area_r >= 0.012,
            rect >= 0.06,
            dom != "grey",
            blue_frac >= 0.02,
        ]
    )
    if not any_structural:
        return True, "no_extractable_connector_visual_cues"
    return False, ""


def build_params_from_uploaded_image(
    base_params: ConnectorCadParams,
    output_dir: Path,
    filename: str | None,
    user_text: str | None,
) -> ConnectorCadParams:
    """Photo tab: visual grammar first; generic_mvp only when decode/extract truly fails."""
    if not filename:
        return base_params.model_copy(
            update={
                "model_origin": "generic_mvp",
                "template_name": "GENERIC_RECTANGULAR_CONNECTOR",
                "uploaded_file_name": None,
                "ai_extraction": _ai_skipped(),
                "appearance_pipeline": {
                    "used": True,
                    "mode": "generic_mvp",
                    "template_name": "GENERIC_RECTANGULAR_CONNECTOR",
                    "selection_reason": "No upload file present.",
                    "preview_color": "grey",
                    "fallback_reason": "no_filename",
                },
            }
        )

    src = output_dir / f"source_{filename}"
    if not src.exists():
        return base_params.model_copy(
            update={
                "model_origin": "generic_mvp",
                "template_name": "GENERIC_RECTANGULAR_CONNECTOR",
                "uploaded_file_name": filename,
                "ai_extraction": _ai_skipped(),
                "appearance_pipeline": {
                    "used": True,
                    "mode": "generic_mvp",
                    "template_name": "GENERIC_RECTANGULAR_CONNECTOR",
                    "selection_reason": "Upload file missing on disk.",
                    "preview_color": "grey",
                    "fallback_reason": "file_missing_on_disk",
                },
                "preview_style": {"base_color": "grey"},
            }
        )

    try:
        feats = extract_image_features(src)
    except Exception as exc:
        return base_params.model_copy(
            update={
                "model_origin": "generic_mvp",
                "template_name": "GENERIC_RECTANGULAR_CONNECTOR",
                "uploaded_file_name": filename,
                "ai_extraction": _ai_skipped(),
                "appearance_pipeline": {
                    "used": True,
                    "mode": "generic_mvp",
                    "template_name": "GENERIC_RECTANGULAR_CONNECTOR",
                    "selection_reason": "Could not decode or analyze image.",
                    "preview_color": "grey",
                    "fallback_reason": f"decode_or_extract_failed:{exc!s}",
                },
                "image_fallback_warning": "無法解析圖像，已回退通用白模。",
            }
        )

    (output_dir / "image_features.json").write_text(
        json.dumps(feats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = summarize_features_for_storage(feats)
    vision = extract_vision_analysis(src, (user_text or "")[:500], summary)
    (output_dir / "vision_report.json").write_text(json.dumps(vision, ensure_ascii=False, indent=2), encoding="utf-8")
    recipe = build_shape_recipe_from_visual_features(feats, vision, {})
    (output_dir / "visual_recipe.json").write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding="utf-8")

    img_w = int(feats.get("width_px") or 1)
    img_h = int(feats.get("height_px") or 1)
    weak, fb_reason = _upload_should_fallback_generic(feats, img_w, img_h)
    preview_color = str(vision.get("likely_color") or feats.get("dominant_color") or "grey")

    unknown_extra = [
        k
        for k in (
            "exact_pitch_mm",
            "exact_cavity_diameter_mm",
            "exact_body_length_mm",
            "exact_connector_outline",
        )
        if k not in (base_params.unknown_fields or [])
    ]
    merged_unknown = list(base_params.unknown_fields or []) + unknown_extra

    if weak:
        return base_params.model_copy(
            update={
                "model_origin": "generic_mvp",
                "template_name": "GENERIC_RECTANGULAR_CONNECTOR",
                "uploaded_file_name": filename,
                "appearance_confidence": "low",
                "unknown_fields": merged_unknown,
                "ai_extraction": _ai_skipped(),
                "appearance_pipeline": {
                    "used": True,
                    "mode": "generic_mvp",
                    "template_name": "GENERIC_RECTANGULAR_CONNECTOR",
                    "selection_reason": "Visual cues insufficient for connector interpretation.",
                    "preview_color": preview_color,
                    "image_features_file": "image_features.json",
                    "vision_report_file": "vision_report.json",
                    "visual_recipe_file": "visual_recipe.json",
                    "fallback_reason": fb_reason,
                },
                "preview_style": {"base_color": preview_color},
                "image_feature_summary": feats,
                "vision_report_summary": vision,
                "visual_recipe": recipe,
                "image_fallback_warning": f"已回退通用白模。原因：{fb_reason}",
            }
        )

    np = _apply_recipe_dimensions(base_params, recipe)
    return np.model_copy(
        update={
            "title": ((user_text or "").strip() or base_params.title)[:80],
            "uploaded_file_name": filename,
            "unknown_fields": merged_unknown,
            "model_origin": "image_upload_approximated",
            "template_name": "VISUAL_GRAMMAR_PROXY",
            "appearance_confidence": str(recipe.get("confidence") or "medium"),
            "preview_style": {"base_color": recipe.get("color") or preview_color},
            "geometry_basis": "visual_shape_grammar",
            "manufacturing_accuracy": "visual_proxy_only",
            "visual_recipe": recipe,
            "image_feature_summary": feats,
            "vision_report_summary": vision,
            "appearance_pipeline": {
                "used": True,
                "mode": "image_upload_approximated",
                "template_name": "VISUAL_GRAMMAR_PROXY",
                "selection_reason": "Direct image upload; visual shape grammar (not per-part template).",
                "preview_color": recipe.get("color"),
                "image_features_file": "image_features.json",
                "vision_report_file": "vision_report.json",
                "visual_recipe_file": "visual_recipe.json",
            },
            "disclaimer": _disclaimer_upload(),
            "warning": PROVISIONAL_WARNING + " " + _disclaimer_upload(),
            "ai_extraction": _ai_skipped(),
            "notes": "Dimensions derived from visual proxy assumptions — confirm before manufacturing.",
        }
    )


def merge_image_search_fallback_notice(params: ConnectorCadParams, meta: dict[str, Any]) -> ConnectorCadParams:
    """Append warning when search API was not configured."""
    if meta.get("image_search", {}).get("status") != "not_configured":
        return params
    note = " 未启用联网图片搜索（IMAGE_SEARCH_*），已回退到 AI / 系列模板 / 通用参数化流程。"
    return params.model_copy(update={"warning": (params.warning or "") + note})
