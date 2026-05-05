from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from services.audit_report import build_audit_report, write_audit_report
from services.cache_integrity import check_registry_cache_integrity, repair_registry_cache
from services.cad_source_resolver import CadSourceResolver
from services.cad_registry import (
    create_registry_item,
    deprecate_registry_item,
    export_registry_snapshot,
    get_registry_item,
    get_registry_item_cache as read_registry_item_cache,
    import_registry_snapshot,
    note_registry_used_in_job,
    refresh_registry_item_cache as rebuild_registry_item_cache,
    review_registry_item,
    update_registry_item,
)
from services.ai_client import get_ai_env, is_ai_configured, preview_api_key
from services.ai_param_extractor import DEFAULT_EXTRACTED, extract_connector_params_with_ai_detailed
from services.appearance_job_steps import (
    configure_image_appearance_pipeline,
    configure_text_appearance_pipeline,
    is_image_upload,
)
from services.connector_params import (
    ConnectorCadParams,
    InputType,
    OFFICIAL_LICENSE_NOTE,
    apply_audit_metadata,
    apply_cad_source_metadata,
    apply_confirmed_params,
    build_official_params,
    build_initial_params,
    mark_failed,
    merge_confirmed_params,
)
from services.domain_policy import classify_source_url
from services.export_service import export_job_files
from services.file_store import create_job_dir, file_path, load_params, new_job_id, save_params, save_upload
from services.image_search_client import search_connector_images
from services.image_search_store import create_search_record, get_search_record, resolve_candidate
from services.official_cad_downloader import can_use_official_cad, download_official_cad, write_official_params
from services.search_to_cad_pipeline import (
    generate_cad_from_search,
    merge_image_search_fallback_notice,
)
from services.search_result_ranker import assess_candidate_generation_risk
from services.source_audit import create_source_manifest, augment_params_json, summarize_manifest
from services.registry_history import get_registry_item_history, verify_registry_history_signatures
from services.registry_search import get_registry_stats, search_registry_items

app = FastAPI(title="Connector CAD Generator", version="0.2.0")
cad_source_resolver = CadSourceResolver()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://127.0.0.1:5174", "http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ImageSearchJobRequest(BaseModel):
    query: str
    selected_image_url: str = ""


class ImageSearchRequest(BaseModel):
    query: str
    provider: str | None = None
    max_results: int | None = None


class SelectedImageJobRequest(BaseModel):
    search_id: str
    candidate_id: str
    query: str | None = None
    accept_part_mismatch_risk: bool = False
    accept_generation_risk: bool = False
    accepted_risk_code: str | None = None


class ManualImageUrlJobRequest(BaseModel):
    query: str
    image_url: str
    title: str = "manual image URL"
    source_url: str = ""


class OfficialUrlJobRequest(BaseModel):
    part_number: str
    manufacturer: str | None = None
    source_url: str
    cad_url: str
    file_type: Literal["step", "stp"] = "step"
    license_note: str = OFFICIAL_LICENSE_NOTE


class RegistryReviewRequest(BaseModel):
    status: Literal["approved", "rejected", "pending_review"]
    reviewed_by: str = "local_admin"
    review_note: str = ""


class RegistryDeprecateRequest(BaseModel):
    replacement_id: str | None = None
    reason: str = "Deprecated by local admin."


class AiTestRequest(BaseModel):
    text: str


def _ai_extraction_skipped_block() -> dict[str, Any]:
    env = get_ai_env()
    return {
        "enabled": False,
        "status": "skipped",
        "provider": env.get("provider", "openai_compatible"),
        "model": env.get("model", "") or "",
        "error": "",
        "extracted": {**DEFAULT_EXTRACTED},
    }


@app.get("/api/ai/status")
def ai_api_status() -> dict[str, Any]:
    env = get_ai_env()
    key = env.get("api_key", "")
    configured = is_ai_configured()
    return {
        "configured": configured,
        "provider": env.get("provider", "openai_compatible"),
        "base_url_set": bool(env.get("base_url")),
        "api_key_set": bool(key),
        "model": env.get("model", "") or "",
        "key_preview": preview_api_key(key) if key else "",
    }


@app.post("/api/ai/test")
def ai_api_test(payload: AiTestRequest) -> dict[str, Any]:
    extracted, meta = extract_connector_params_with_ai_detailed((payload.text or "").strip())
    return {"ok": meta.get("status") == "success", "extracted": extracted}


@app.post("/api/connector-cad/jobs")
async def create_job(request: Request) -> dict[str, Any]:
    input_type, text, file, incoming_params, preferred_revision, preferred_version_label = await parse_job_request(request)
    job_id = new_job_id()
    output_dir = create_job_dir(job_id)
    filename = save_upload(job_id, file)
    cad_source = cad_source_resolver.resolve(
        text=text,
        preferred_revision=preferred_revision,
        preferred_version_label=preferred_version_label,
    )

    if can_use_official_cad(cad_source):
        params = build_official_params(input_type=input_type, text=text, cad_source=cad_source)
        params = params.model_copy(update={"ai_extraction": _ai_extraction_skipped_block()})
        try:
            generated_files = download_official_cad(cad_source, output_dir)
            write_official_params(params, output_dir)
            params = finalize_source_audit(job_id, output_dir, params, {**cad_source, "official_cad_downloaded": True}, generated_files)
            save_params(job_id, params)
            note_registry_used_in_job(cad_source, job_id)
        except Exception as exc:
            params = mark_failed(params, str(exc))
            save_params(job_id, params)
        return job_payload(job_id, params)

    params = build_initial_params(input_type=input_type, text=text, filename=filename)
    params = apply_cad_source_metadata(params, cad_source)

    if input_type == "text" and (text or "").strip():
        tried, search_meta = generate_cad_from_search((text or "").strip(), output_dir, params, None)
        if tried is not None:
            params = tried
        else:
            params = configure_text_appearance_pipeline(params, text.strip())
            params = merge_image_search_fallback_notice(params, search_meta)
    elif input_type in ("photo", "drawing") and is_image_upload(filename):
        params = configure_image_appearance_pipeline(params, output_dir, filename, text)
    elif input_type in ("photo", "drawing"):
        params = params.model_copy(
            update={
                "model_origin": "generic_mvp",
                "template_name": "GENERIC_RECTANGULAR_CONNECTOR",
                "appearance_confidence": "low",
                "ai_extraction": _ai_extraction_skipped_block(),
                "appearance_pipeline": {
                    "used": True,
                    "mode": "generic_mvp",
                    "template_name": "GENERIC_RECTANGULAR_CONNECTOR",
                    "selection_reason": "Non-image upload: using upgraded generic rectangular template (not OCR).",
                    "preview_color": "grey",
                    "image_features_file": None,
                    "vision_report_file": None,
                },
                "preview_style": {"base_color": "grey"},
            }
        )
    else:
        params = params.model_copy(update={"ai_extraction": _ai_extraction_skipped_block()})

    params = apply_confirmed_params(params, incoming_params)
    try:
        generated_files = export_job_files(params, output_dir)
        params = finalize_source_audit(job_id, output_dir, params, {**cad_source, "official_cad_downloaded": False}, generated_files)
        save_params(job_id, params)
    except Exception as exc:
        params = mark_failed(params, str(exc))
        save_params(job_id, params)
    return job_payload(job_id, params)


@app.post("/api/connector-cad/jobs/from-image-search")
def create_job_from_image_search(payload: ImageSearchJobRequest) -> dict[str, Any]:
    job_id = new_job_id()
    output_dir = create_job_dir(job_id)
    q = (payload.query or "").strip()
    cad_source = cad_source_resolver.resolve(text=q)
    if can_use_official_cad(cad_source):
        params = build_official_params(input_type="text", text=q, cad_source=cad_source)
        params = params.model_copy(update={"ai_extraction": _ai_extraction_skipped_block()})
        try:
            generated_files = download_official_cad(cad_source, output_dir)
            write_official_params(params, output_dir)
            params = finalize_source_audit(job_id, output_dir, params, {**cad_source, "official_cad_downloaded": True}, generated_files)
            save_params(job_id, params)
            note_registry_used_in_job(cad_source, job_id)
        except Exception as exc:
            params = mark_failed(params, str(exc))
            save_params(job_id, params)
        return job_payload(job_id, params)

    params = build_initial_params(input_type="text", text=q, filename=None)
    params = apply_cad_source_metadata(params, cad_source)
    sel_url = (payload.selected_image_url or "").strip() or None
    tried, search_meta = generate_cad_from_search(q, output_dir, params, sel_url)
    if tried is not None:
        params = tried
    else:
        params = configure_text_appearance_pipeline(params, q)
        params = merge_image_search_fallback_notice(params, search_meta)
    try:
        generated_files = export_job_files(params, output_dir)
        params = finalize_source_audit(job_id, output_dir, params, {**cad_source, "official_cad_downloaded": False}, generated_files)
        save_params(job_id, params)
    except Exception as exc:
        params = mark_failed(params, str(exc))
        save_params(job_id, params)
    return job_payload(job_id, params)


@app.post("/api/connector-cad/image-search")
def create_connector_image_search(payload: ImageSearchRequest) -> dict[str, Any]:
    query = (payload.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    pack = search_connector_images(query, payload.max_results, payload.provider)
    return create_search_record(
        query=pack.get("query") or query,
        provider=pack.get("provider") or payload.provider or "",
        status=pack.get("status") or "failed",
        results=pack.get("results") or [],
        warnings=pack.get("warnings") or [],
        expanded_query=pack.get("expanded_query") or pack.get("query") or query,
        ranker=pack.get("ranker") or {},
        refined_searches=pack.get("refined_searches") or [],
        exact_match_found=pack.get("exact_match_found"),
        match_summary=pack.get("match_summary") or {},
    )


@app.get("/api/connector-cad/image-search/{search_id}")
def get_connector_image_search(search_id: str) -> dict[str, Any]:
    return get_search_record(search_id)


@app.post("/api/connector-cad/jobs/from-selected-image")
def create_job_from_selected_image(payload: SelectedImageJobRequest) -> dict[str, Any]:
    record, candidate = resolve_candidate(payload.search_id, payload.candidate_id)
    part_match = candidate.get("part_match") or {}
    match_evidence = candidate.get("match_evidence") or {}
    generation_risk = candidate.get("generation_risk") or assess_candidate_generation_risk(candidate)
    candidate["generation_risk"] = generation_risk
    risk_accepted = bool(payload.accept_generation_risk or payload.accept_part_mismatch_risk)
    if generation_risk.get("requires_confirmation") and not risk_accepted:
        raise HTTPException(
            status_code=409,
            detail={
                "status": "requires_confirmation",
                "error": "Selected image requires confirmation before CAD generation.",
                "generation_risk": generation_risk,
                "part_match": part_match,
                "match_evidence": match_evidence,
                "message": "Set accept_generation_risk=true to continue.",
            },
        )
    query = (payload.query or record.get("query") or candidate.get("title") or "").strip()
    return create_visual_search_job(
        query=query,
        selected_image_url=str(candidate.get("image_url") or candidate.get("thumbnail_url") or ""),
        selected_image=candidate,
        search_pack=record,
        part_mismatch_risk_accepted=bool(payload.accept_part_mismatch_risk),
        generation_risk_accepted=risk_accepted,
        accepted_risk_code=payload.accepted_risk_code or generation_risk.get("confirmation_code") or "",
    )


@app.post("/api/connector-cad/jobs/from-manual-image-url")
def create_job_from_manual_image_url(payload: ManualImageUrlJobRequest) -> dict[str, Any]:
    query = (payload.query or "").strip()
    image_url = (payload.image_url or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    if not image_url:
        raise HTTPException(status_code=400, detail="image_url is required")
    selected = {
        "id": "manual_image",
        "rank": 1,
        "title": payload.title,
        "image_url": image_url,
        "thumbnail_url": image_url,
        "source_url": payload.source_url or image_url,
        "domain": "",
        "rank_reason": "User supplied manual image URL.",
        "part_match": {
            "match_level": "none",
            "query_part_number": query,
            "matched_part_number": "",
            "reason": "Manual image URL is not verified against the query part number.",
        },
    }
    search_pack = {
        "search_id": None,
        "query": query,
        "provider": "manual_url",
        "status": "manual",
        "results": [selected],
        "warnings": [],
        "manual_image_url_unverified": True,
        "match_summary": {
            "exact": 0,
            "weak": 0,
            "near_miss": 0,
            "none": 1,
            "has_exact": False,
            "requires_part_mismatch_confirmation": False,
        },
    }
    return create_visual_search_job(query=query, selected_image_url=image_url, selected_image=selected, search_pack=search_pack)


@app.get("/api/test-assets/connector_reference_1_968970_1.png")
@app.head("/api/test-assets/connector_reference_1_968970_1.png")
def get_connector_reference_test_asset() -> FileResponse:
    path = Path(__file__).resolve().parent / "test_assets" / "connector_reference_1_968970_1.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Test asset not found")
    return FileResponse(path, media_type="image/png", filename=path.name)


@app.post("/api/connector-cad/jobs/from-official-url")
async def create_job_from_official_url(payload: OfficialUrlJobRequest) -> dict[str, Any]:
    job_id = new_job_id()
    output_dir = create_job_dir(job_id)
    source_domain = classify_source_url(payload.source_url or payload.cad_url)
    source_type = "third_party" if source_domain["category"] == "third_party_repository" else "official_cad"
    cad_source = {
        "manufacturer": payload.manufacturer,
        "part_number": payload.part_number,
        "source_type": source_type,
        "cad_url": payload.cad_url,
        "source_url": payload.source_url,
        "file_type": payload.file_type,
        "confidence": "high" if source_domain["is_approved"] else "manual_pending",
        "requires_manual_url": False,
        "license_note": payload.license_note,
    }
    params = build_official_params(input_type="text", text=payload.part_number, cad_source=cad_source)
    params = params.model_copy(update={"ai_extraction": _ai_extraction_skipped_block()})
    try:
        generated_files = download_official_cad(cad_source, output_dir)
        write_official_params(params, output_dir)
        params = finalize_source_audit(job_id, output_dir, params, {**cad_source, "official_cad_downloaded": True}, generated_files)
        save_params(job_id, params)
    except Exception as exc:
        params = mark_failed(params, str(exc))
        save_params(job_id, params)
    return job_payload(job_id, params)


def create_visual_search_job(
    query: str,
    selected_image_url: str,
    selected_image: dict[str, Any],
    search_pack: dict[str, Any],
    part_mismatch_risk_accepted: bool = False,
    generation_risk_accepted: bool = False,
    accepted_risk_code: str = "",
) -> dict[str, Any]:
    if not selected_image_url:
        raise HTTPException(status_code=400, detail="selected image URL is empty")
    job_id = new_job_id()
    output_dir = create_job_dir(job_id)
    cad_source = cad_source_resolver.resolve(text=query)
    params = build_initial_params(input_type="text", text=query, filename=None)
    params = apply_cad_source_metadata(params, cad_source)
    tried, search_meta = generate_cad_from_search(
        query,
        output_dir,
        params,
        selected_image_url=selected_image_url,
        selected_image=selected_image,
        search_pack_override=search_pack,
        part_mismatch_risk_accepted=part_mismatch_risk_accepted,
        generation_risk_accepted=generation_risk_accepted,
        accepted_risk_code=accepted_risk_code,
    )
    if tried is not None:
        params = tried
    else:
        params = configure_text_appearance_pipeline(params, query)
        params = merge_image_search_fallback_notice(params, search_meta)
    try:
        generated_files = export_job_files(params, output_dir)
        params = finalize_source_audit(job_id, output_dir, params, {**cad_source, "official_cad_downloaded": False}, generated_files)
        save_params(job_id, params)
    except Exception as exc:
        params = mark_failed(params, str(exc))
        save_params(job_id, params)
    return job_payload(job_id, params)


@app.get("/api/connector-cad/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    return job_payload(job_id, load_params(job_id))


@app.get("/api/cad-registry/items")
def list_cad_registry_items(
    q: str | None = None,
    status: str | None = None,
    manufacturer: str | None = None,
    part_number: str | None = None,
    source_category: str | None = None,
    cache_status: str | None = None,
    revision: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
) -> dict[str, Any]:
    return search_registry_items(
        query=q,
        status=status,
        manufacturer=manufacturer,
        part_number=part_number,
        source_category=source_category,
        cache_status=cache_status,
        revision=revision,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@app.get("/api/cad-registry/stats")
def get_cad_registry_stats() -> dict[str, Any]:
    return get_registry_stats()


@app.post("/api/cad-registry/items")
async def create_cad_registry_item(payload: dict[str, Any]) -> dict[str, Any]:
    return create_registry_item(payload)


@app.get("/api/cad-registry/items/{item_id}")
def get_cad_registry_item(item_id: str) -> dict[str, Any]:
    return get_registry_item(item_id)


@app.patch("/api/cad-registry/items/{item_id}")
async def patch_cad_registry_item(item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return update_registry_item(item_id, payload)


@app.post("/api/cad-registry/items/{item_id}/review")
def review_cad_registry_item(item_id: str, payload: RegistryReviewRequest) -> dict[str, Any]:
    return review_registry_item(
        item_id=item_id,
        status=payload.status,
        reviewed_by=payload.reviewed_by,
        review_note=payload.review_note,
    )


@app.post("/api/cad-registry/items/{item_id}/deprecate")
def deprecate_cad_registry_item(item_id: str, payload: RegistryDeprecateRequest) -> dict[str, Any]:
    return deprecate_registry_item(item_id, replacement_id=payload.replacement_id, reason=payload.reason)


@app.get("/api/cad-registry/items/{item_id}/history")
def get_cad_registry_item_history(item_id: str) -> dict[str, Any]:
    return get_registry_item_history(item_id)


@app.post("/api/cad-registry/items/{item_id}/refresh-cache")
def refresh_cad_registry_item_cache(item_id: str) -> dict[str, Any]:
    return rebuild_registry_item_cache(item_id)


@app.get("/api/cad-registry/items/{item_id}/cache")
def get_cad_registry_item_cache(item_id: str) -> dict[str, Any]:
    return read_registry_item_cache(item_id)


@app.post("/api/cad-registry/cache/check")
def check_cad_registry_cache() -> dict[str, Any]:
    return check_registry_cache_integrity()


@app.post("/api/cad-registry/items/{item_id}/cache/check")
def check_cad_registry_item_cache(item_id: str) -> dict[str, Any]:
    return check_registry_cache_integrity(item_id)


@app.post("/api/cad-registry/cache/repair")
def repair_cad_registry_cache() -> dict[str, Any]:
    return repair_registry_cache()


@app.post("/api/cad-registry/items/{item_id}/cache/repair")
def repair_cad_registry_item_cache(item_id: str) -> dict[str, Any]:
    return repair_registry_cache(item_id)


@app.get("/api/cad-registry/audit/verify")
def verify_cad_registry_audit() -> dict[str, Any]:
    return verify_registry_history_signatures()


@app.get("/api/cad-registry/audit/report")
def get_cad_registry_audit_report() -> dict[str, Any]:
    return build_audit_report()


@app.get("/api/cad-registry/audit/report/download")
@app.head("/api/cad-registry/audit/report/download")
def download_cad_registry_audit_report() -> FileResponse:
    _, path = write_audit_report()
    return FileResponse(path, media_type="application/json", filename=Path(path).name)


@app.get("/api/cad-registry/export")
def export_cad_registry() -> dict[str, Any]:
    return export_registry_snapshot()


@app.post("/api/cad-registry/import")
async def import_cad_registry(payload: dict[str, Any]) -> dict[str, Any]:
    return import_registry_snapshot(payload)


@app.post("/api/connector-cad/jobs/{job_id}/confirm-params")
async def confirm_params(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    params = merge_confirmed_params(load_params(job_id), payload)
    output_dir = create_job_dir(job_id)
    try:
        generated_files = export_job_files(params, output_dir)
        params = finalize_source_audit(job_id, output_dir, params, source_result_from_params(params), generated_files)
        save_params(job_id, params)
    except Exception as exc:
        params = mark_failed(params, str(exc))
        save_params(job_id, params)
    return job_payload(job_id, params)


@app.get("/api/connector-cad/jobs/{job_id}/files/model.step")
@app.head("/api/connector-cad/jobs/{job_id}/files/model.step")
def download_step(job_id: str) -> FileResponse:
    return download_file(job_id, "model.step", "application/step")


@app.get("/api/connector-cad/jobs/{job_id}/files/model.stl")
@app.head("/api/connector-cad/jobs/{job_id}/files/model.stl")
def download_stl(job_id: str) -> FileResponse:
    return download_file(job_id, "model.stl", "model/stl")


@app.get("/api/connector-cad/jobs/{job_id}/files/drawing.dxf")
@app.head("/api/connector-cad/jobs/{job_id}/files/drawing.dxf")
def download_dxf(job_id: str) -> FileResponse:
    return download_file(job_id, "drawing.dxf", "application/dxf")


@app.get("/api/connector-cad/jobs/{job_id}/files/params.json")
@app.head("/api/connector-cad/jobs/{job_id}/files/params.json")
def download_params(job_id: str) -> FileResponse:
    return download_file(job_id, "params.json", "application/json")


@app.get("/api/connector-cad/jobs/{job_id}/files/source_manifest.json")
@app.head("/api/connector-cad/jobs/{job_id}/files/source_manifest.json")
def download_source_manifest(job_id: str) -> FileResponse:
    return download_file(job_id, "source_manifest.json", "application/json")


@app.get("/api/connector-cad/jobs/{job_id}/files/image_features.json")
@app.head("/api/connector-cad/jobs/{job_id}/files/image_features.json")
def download_image_features(job_id: str) -> FileResponse:
    return download_file(job_id, "image_features.json", "application/json")


@app.get("/api/connector-cad/jobs/{job_id}/files/vision_report.json")
@app.head("/api/connector-cad/jobs/{job_id}/files/vision_report.json")
def download_vision_report(job_id: str) -> FileResponse:
    return download_file(job_id, "vision_report.json", "application/json")


@app.get("/api/connector-cad/jobs/{job_id}/files/image_search_results.json")
@app.head("/api/connector-cad/jobs/{job_id}/files/image_search_results.json")
def download_image_search_results(job_id: str) -> FileResponse:
    return download_file(job_id, "image_search_results.json", "application/json")


@app.get("/api/connector-cad/jobs/{job_id}/files/selected_image.json")
@app.head("/api/connector-cad/jobs/{job_id}/files/selected_image.json")
def download_selected_image_meta(job_id: str) -> FileResponse:
    return download_file(job_id, "selected_image.json", "application/json")


@app.get("/api/connector-cad/jobs/{job_id}/files/visual_recipe.json")
@app.head("/api/connector-cad/jobs/{job_id}/files/visual_recipe.json")
def download_visual_recipe(job_id: str) -> FileResponse:
    return download_file(job_id, "visual_recipe.json", "application/json")


async def parse_job_request(request: Request) -> tuple[InputType, str | None, Any, dict[str, Any], str | None, str | None]:
    content_type = request.headers.get("content-type", "")
    file = None
    incoming_params: dict[str, Any] = {}
    preferred_revision = None
    preferred_version_label = None

    if content_type.startswith("application/json"):
        payload = await request.json()
        input_type = payload.get("input_type")
        text = payload.get("text")
        incoming_params = payload.get("params") or {}
        preferred_revision = payload.get("preferred_revision")
        preferred_version_label = payload.get("preferred_version_label")
    else:
        form = await request.form()
        input_type = form.get("input_type")
        text = form.get("text")
        file = form.get("file")

    if input_type == "text" and not (text or "").strip():
        raise HTTPException(status_code=400, detail="text is required when input_type=text")
    if input_type in {"drawing", "photo"} and file is None:
        raise HTTPException(status_code=400, detail="file is required when input_type is drawing or photo")
    if input_type not in {"text", "drawing", "photo"}:
        raise HTTPException(status_code=400, detail="input_type must be text, drawing, or photo")
    return input_type, text, file, incoming_params, preferred_revision, preferred_version_label


def finalize_source_audit(
    job_id: str,
    output_dir: Path,
    params: ConnectorCadParams,
    source_result: dict[str, Any],
    generated_files: dict[str, Any],
) -> ConnectorCadParams:
    manifest = create_source_manifest(
        job_id=job_id,
        output_dir=output_dir,
        source_result=source_result,
        generated_files=generated_files,
        model_origin=params.model_origin,
        status=params.status,
    )
    augment_params_json(output_dir, manifest)
    manifest = create_source_manifest(
        job_id=job_id,
        output_dir=output_dir,
        source_result=source_result,
        generated_files=generated_files,
        model_origin=params.model_origin,
        status=params.status,
    )
    augment_params_json(output_dir, manifest)
    return apply_audit_metadata(params, manifest)


def source_result_from_params(params: ConnectorCadParams) -> dict[str, Any]:
    return {
        "source_type": params.source_type,
        "source_url": params.source_url,
        "cad_url": params.cad_url,
        "license_note": params.license_note,
        "official_cad_downloaded": params.official_cad_downloaded,
        "registry_item_id": params.registry_item_id,
        "registry_candidate_id": params.registry_candidate_id,
        "registry_status": params.registry_status,
        "revision": params.revision,
        "version_label": params.version_label,
        "registry_sha256": params.registry_sha256,
        "registry_cache_status": params.registry_cache_status,
        "cached_file_used": params.cached_file_used,
        "cached_file_sha256": params.cached_file_sha256,
        "cache_metadata_path": params.cache_metadata_path,
        "selection_reason": params.selection_reason,
        "available_versions": params.available_versions,
        "preferred_revision": params.preferred_revision,
        "preferred_version_label": params.preferred_version_label,
    }


def job_payload(job_id: str, params: ConnectorCadParams) -> dict[str, Any]:
    manifest = load_source_manifest(job_id)
    source_domain = manifest.get("source_domain") if manifest else classify_source_url(params.source_url or params.cad_url)
    source_audit_summary = summarize_manifest(manifest) if manifest else {
        "model_origin": params.model_origin,
        "source_type": params.source_type,
        "source_category": source_domain.get("category", "unknown"),
        "is_approved_source": bool(source_domain.get("is_approved", False)),
        "has_sha256": bool(params.file_hashes),
        "production_use_warning": "Verify CAD source, revision, and manufacturer terms before using for production.",
        "downloaded_at": "",
    }
    return {
        "job_id": job_id,
        "status": params.status,
        "warning": params.warning,
        "error": params.error,
        "params": params.model_dump(),
        "source_manifest_url": f"/api/connector-cad/jobs/{job_id}/files/source_manifest.json",
        "source_domain": source_domain,
        "source_audit_summary": source_audit_summary,
        "files": {
            "model_step": f"/api/connector-cad/jobs/{job_id}/files/model.step",
            "model_stl": f"/api/connector-cad/jobs/{job_id}/files/model.stl",
            "drawing_dxf": f"/api/connector-cad/jobs/{job_id}/files/drawing.dxf",
            "params_json": f"/api/connector-cad/jobs/{job_id}/files/params.json",
            "source_manifest": f"/api/connector-cad/jobs/{job_id}/files/source_manifest.json",
            "image_features": f"/api/connector-cad/jobs/{job_id}/files/image_features.json",
            "vision_report": f"/api/connector-cad/jobs/{job_id}/files/vision_report.json",
            "image_search_results": f"/api/connector-cad/jobs/{job_id}/files/image_search_results.json",
            "selected_image": f"/api/connector-cad/jobs/{job_id}/files/selected_image.json",
            "visual_recipe": f"/api/connector-cad/jobs/{job_id}/files/visual_recipe.json",
        },
    }


def load_source_manifest(job_id: str) -> dict[str, Any] | None:
    path = create_job_dir(job_id) / "source_manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def download_file(job_id: str, filename: str, media_type: str) -> FileResponse:
    path = file_path(job_id, filename)
    return FileResponse(path, media_type=media_type, filename=filename)
