from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from services.connector_params import OFFICIAL_LICENSE_NOTE
from services.domain_policy import classify_source_url
from services.json_store import atomic_write_json
from services.registry_cache import get_cached_registry_file, refresh_registry_cache, validate_cached_file
from services.registry_history import append_registry_event, list_registry_events
from services.registry_store import DATA_ROOT, REGISTRY_PATH, load_registry, save_registry
from services.registry_versioning import select_best_registry_item

VALID_FILE_TYPES = {"step", "stp", "stl", "dxf", "iges", "igs"}


def normalize_part_key(manufacturer: str | None, part_number: str) -> str:
    maker = _normalize(manufacturer or "")
    part = _normalize(part_number)
    return f"{maker}::{part}" if maker else part


def create_registry_item(payload: dict[str, Any]) -> dict[str, Any]:
    file_type = _validated_file_type(payload.get("file_type"))
    part_number = str(payload.get("part_number", "")).strip()
    if not part_number:
        raise HTTPException(status_code=400, detail="part_number is required")
    manufacturer = (payload.get("manufacturer") or "").strip()
    cad_url = (payload.get("cad_url") or "").strip()
    if not cad_url:
        raise HTTPException(status_code=400, detail="cad_url is required")

    source_url = (payload.get("source_url") or "").strip()
    domain = classify_source_url(source_url or cad_url)
    now = _now()
    item = {
        "id": uuid.uuid4().hex,
        "manufacturer": manufacturer,
        "part_number": part_number,
        "normalized_key": normalize_part_key(manufacturer, part_number),
        "title": payload.get("title") or " ".join(part for part in [manufacturer, part_number] if part),
        "source_url": source_url,
        "cad_url": cad_url,
        "file_type": file_type,
        "source_category": domain["category"],
        "domain": domain["domain"],
        "source_domain_approved": bool(domain["is_approved"]),
        "source_warning": domain["warning"],
        "status": payload.get("status") if payload.get("status") in {"draft", "pending_review"} else "pending_review",
        "revision": payload.get("revision") or "unknown",
        "version_label": payload.get("version_label") or "v1",
        "sha256": "",
        "file_size_bytes": None,
        "cache_status": "not_cached",
        "cached_at": "",
        "cached_file_path": "",
        "cache_metadata_path": "",
        "license_note": payload.get("license_note") or OFFICIAL_LICENSE_NOTE,
        "review": {"reviewed_by": "", "reviewed_at": "", "review_note": ""},
        "created_at": now,
        "updated_at": now,
        "deprecated_at": None,
        "replacement_id": None,
    }
    data = load_registry()
    data["items"].append(item)
    save_registry(data)
    append_registry_event(item["id"], "created", payload.get("actor", "local_admin"), before={}, after=item, note="Registry item created.")
    return item


def list_registry_items(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}
    items = load_registry().get("items", [])
    for key in ["status", "manufacturer", "part_number", "source_category"]:
        expected = filters.get(key)
        if expected:
            items = [item for item in items if str(item.get(key, "")).lower() == str(expected).lower()]
    return sorted(items, key=lambda item: item.get("updated_at", ""), reverse=True)


def get_registry_item(item_id: str) -> dict[str, Any]:
    for item in load_registry().get("items", []):
        if item.get("id") == item_id:
            return item
    raise HTTPException(status_code=404, detail="Registry item not found")


def update_registry_item(item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = load_registry()
    for index, item in enumerate(data.get("items", [])):
        if item.get("id") != item_id:
            continue
        before = dict(item)
        updated = dict(item)
        for key in ["manufacturer", "part_number", "title", "source_url", "cad_url", "revision", "version_label", "license_note"]:
            if key in payload:
                updated[key] = payload[key]
        if "file_type" in payload:
            updated["file_type"] = _validated_file_type(payload["file_type"])
        domain = classify_source_url(updated.get("source_url") or updated.get("cad_url"))
        updated["normalized_key"] = normalize_part_key(updated.get("manufacturer"), updated["part_number"])
        updated["source_category"] = domain["category"]
        updated["domain"] = domain["domain"]
        updated["source_domain_approved"] = bool(domain["is_approved"])
        updated["source_warning"] = domain["warning"]
        updated["updated_at"] = _now()
        if any(key in payload for key in ["cad_url", "file_type"]):
            updated.update({"sha256": "", "file_size_bytes": None, "cache_status": "not_cached", "cached_file_path": "", "cache_metadata_path": "", "cached_at": ""})
            if updated["status"] == "approved":
                updated["status"] = "pending_review"
        data["items"][index] = updated
        save_registry(data)
        append_registry_event(item_id, "updated", payload.get("actor", "local_admin"), before=before, after=updated, note="Registry item updated.")
        return updated
    raise HTTPException(status_code=404, detail="Registry item not found")


def review_registry_item(item_id: str, status: str, reviewed_by: str, review_note: str) -> dict[str, Any]:
    if status not in {"approved", "rejected", "pending_review"}:
        raise HTTPException(status_code=400, detail="review status must be approved, rejected, or pending_review")
    data = load_registry()
    for index, item in enumerate(data.get("items", [])):
        if item.get("id") != item_id:
            continue
        before = dict(item)
        updated = dict(item)
        now = _now()
        if status == "approved":
            try:
                cached = refresh_registry_cache(item_id)
                updated.update(cached)
            except Exception as exc:
                updated["status"] = "failed_review"
                updated["review"] = {"reviewed_by": reviewed_by, "reviewed_at": now, "review_note": f"{review_note} Cache failed: {exc}"}
                updated["updated_at"] = now
                data["items"][index] = updated
                save_registry(data)
                append_registry_event(item_id, "rejected", reviewed_by, before=before, after=updated, note=f"Approval failed: {exc}")
                raise HTTPException(status_code=400, detail=f"CAD file could not be cached: {exc}")
        updated["status"] = status
        updated["review"] = {"reviewed_by": reviewed_by, "reviewed_at": now, "review_note": review_note}
        updated["updated_at"] = now
        data = load_registry()
        for save_index, save_item in enumerate(data.get("items", [])):
            if save_item.get("id") == item_id:
                data["items"][save_index] = updated
                break
        save_registry(data)
        event_type = "reviewed" if status == "approved" else "rejected" if status == "rejected" else "updated"
        append_registry_event(item_id, event_type, reviewed_by, before=before, after=updated, note=review_note)
        return updated
    raise HTTPException(status_code=404, detail="Registry item not found")


def deprecate_registry_item(item_id: str, replacement_id: str | None = None, reason: str | None = None) -> dict[str, Any]:
    data = load_registry()
    for index, item in enumerate(data.get("items", [])):
        if item.get("id") != item_id:
            continue
        before = dict(item)
        updated = {**item, "status": "deprecated", "deprecated_at": _now(), "replacement_id": replacement_id or None, "updated_at": _now()}
        updated["review"] = {**updated.get("review", {}), "reviewed_at": updated["updated_at"], "review_note": reason or "Deprecated by local admin."}
        data["items"][index] = updated
        save_registry(data)
        append_registry_event(item_id, "deprecated", "local_admin", before=before, after=updated, note=reason or "Deprecated by local admin.")
        return updated
    raise HTTPException(status_code=404, detail="Registry item not found")


def find_approved_cad_source(
    manufacturer: str | None = None,
    part_number: str | None = None,
    text: str | None = None,
    preferred_revision: str | None = None,
    preferred_version_label: str | None = None,
) -> dict[str, Any] | None:
    items = load_registry().get("items", [])
    matches = _find_matches_any_status(items, manufacturer, part_number, text)
    selection = select_best_registry_item(matches, preferred_revision, preferred_version_label)
    selected = selection.get("selected_item")
    if selected:
        try:
            if not validate_cached_file(selected):
                selected = refresh_registry_cache(selected["id"])
        except Exception as exc:
            return _candidate_from_item(
                selected,
                fallback_reason=f"Approved CAD cache invalid and refresh failed: {exc}",
                selection=selection,
            )
        return _source_from_registry_item(selected, selection, preferred_revision, preferred_version_label)

    pending = [item for item in matches if item.get("status") == "pending_review"]
    if pending:
        return _candidate_from_item(
            sorted(pending, key=lambda item: item.get("updated_at", ""), reverse=True)[0],
            fallback_reason="CAD source exists but is not approved",
            selection=selection,
        )
    return None


def refresh_registry_item_cache(item_id: str) -> dict[str, Any]:
    return refresh_registry_cache(item_id)


def get_registry_item_cache(item_id: str) -> dict[str, Any]:
    item = get_registry_item(item_id)
    cache = get_cached_registry_file(item_id)
    return {**cache, "item_cache_status": item.get("cache_status", "not_cached"), "sha256": item.get("sha256"), "file_size_bytes": item.get("file_size_bytes")}


def export_registry_snapshot() -> dict[str, Any]:
    snapshot = {"exported_at": _now(), "registry": load_registry(), "history": {"events": list_registry_events()}}
    exports = DATA_ROOT / "registry_exports"
    exports.mkdir(parents=True, exist_ok=True)
    atomic_write_json(exports / f"cad_registry_export_{_filename_stamp()}.json", snapshot)
    return snapshot


def import_registry_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    backup = REGISTRY_PATH.with_name(f"cad_registry.backup.{_filename_stamp()}.json")
    if REGISTRY_PATH.exists():
        shutil.copyfile(REGISTRY_PATH, backup)
    incoming_items = (payload.get("registry") or payload).get("items", [])
    data = load_registry()
    existing = {item.get("id"): item for item in data.get("items", [])}
    imported = skipped = errors = 0
    for item in incoming_items:
        try:
            item_id = item.get("id")
            if not item_id:
                errors += 1
                continue
            current = existing.get(item_id)
            if current and current.get("updated_at", "") >= item.get("updated_at", ""):
                skipped += 1
                continue
            if current:
                data["items"] = [item if existing_item.get("id") == item_id else existing_item for existing_item in data["items"]]
            else:
                data["items"].append(item)
            imported += 1
        except Exception:
            errors += 1
    save_registry(data)
    return {"imported": imported, "skipped": skipped, "errors": errors, "backup_path": str(backup)}


def note_registry_used_in_job(cad_source: dict[str, Any], job_id: str) -> None:
    item_id = cad_source.get("registry_item_id")
    if item_id:
        append_registry_event(item_id, "used_in_job", "system", before={}, after={"id": item_id}, note=f"Used in job {job_id}.")


def _find_matches_any_status(items: list[dict[str, Any]], manufacturer: str | None, part_number: str | None, text: str | None) -> list[dict[str, Any]]:
    exact_key = normalize_part_key(manufacturer, part_number) if part_number else ""
    normalized_part = _normalize(part_number or "")
    normalized_text = _normalize(text or "")
    matches = []
    for item in items:
        item_part = _normalize(item.get("part_number", ""))
        if exact_key and item.get("normalized_key") == exact_key:
            matches.append(item)
        elif normalized_part and item_part == normalized_part:
            matches.append(item)
        elif normalized_text and item_part and item_part in normalized_text:
            matches.append(item)
    return matches


def _source_from_registry_item(item: dict[str, Any], selection: dict[str, Any], preferred_revision: str | None, preferred_version_label: str | None) -> dict[str, Any]:
    source_type = "third_party" if item.get("source_category") == "third_party_repository" else "official_cad"
    return {
        "source_type": source_type,
        "manufacturer": item.get("manufacturer"),
        "part_number": item.get("part_number"),
        "cad_url": item.get("cad_url", ""),
        "source_url": item.get("source_url", ""),
        "file_type": item.get("file_type", "step"),
        "confidence": "high",
        "requires_manual_url": False,
        "license_note": item.get("license_note", OFFICIAL_LICENSE_NOTE),
        "registry_item_id": item.get("id"),
        "registry_status": item.get("status"),
        "revision": item.get("revision"),
        "version_label": item.get("version_label"),
        "registry_sha256": item.get("sha256", ""),
        "registry_file_size_bytes": item.get("file_size_bytes"),
        "registry_cache_status": item.get("cache_status", "not_cached"),
        "cached_file_path": item.get("cached_file_path", ""),
        "cache_metadata_path": item.get("cache_metadata_path", ""),
        "cached_file_used": bool(item.get("cached_file_path")),
        "cached_file_sha256": item.get("sha256", ""),
        "cached_at": item.get("cached_at", ""),
        "selection_reason": selection.get("selection_reason"),
        "available_versions": selection.get("available_versions", []),
        "preferred_revision": preferred_revision,
        "preferred_version_label": preferred_version_label,
        "source_category": item.get("source_category"),
    }


def _candidate_from_item(item: dict[str, Any], fallback_reason: str, selection: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_type": "official_candidate",
        "confidence": "manual_pending",
        "fallback": "parametric_mvp",
        "fallback_reason": fallback_reason,
        "registry_candidate_id": item.get("id"),
        "registry_item_id": item.get("id"),
        "manufacturer": item.get("manufacturer"),
        "part_number": item.get("part_number"),
        "source_url": item.get("source_url", ""),
        "cad_url": item.get("cad_url", ""),
        "revision": item.get("revision"),
        "version_label": item.get("version_label"),
        "license_note": item.get("license_note", OFFICIAL_LICENSE_NOTE),
        "selection_reason": selection.get("selection_reason"),
        "available_versions": selection.get("available_versions", []),
    }


def _validated_file_type(value: Any) -> str:
    file_type = str(value or "").lower()
    if file_type not in VALID_FILE_TYPES:
        raise HTTPException(status_code=400, detail="file_type must be step/stp/stl/dxf/iges/igs")
    return file_type


def _normalize(value: str) -> str:
    import re
    return re.sub(r"[^A-Z0-9-]+", " ", value.upper()).strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _filename_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
