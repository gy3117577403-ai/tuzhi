from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.registry_cache import refresh_registry_cache
from services.registry_history import append_registry_event
from services.registry_store import load_registry


def check_registry_cache_integrity(item_id: str | None = None) -> dict[str, Any]:
    items = load_registry().get("items", [])
    if item_id:
        items = [item for item in items if item.get("id") == item_id]
    else:
        items = [item for item in items if item.get("status") == "approved" or item.get("cache_status") == "cached"]
    results = [_check_item(item) for item in items]
    summary = {
        "checked": len(results),
        "ok": sum(1 for item in results if item["status"] == "ok"),
        "missing": sum(1 for item in results if item["status"] == "missing"),
        "hash_mismatch": sum(1 for item in results if item["status"] == "hash_mismatch"),
        "size_mismatch": sum(1 for item in results if item["status"] == "size_mismatch"),
        "not_cached": sum(1 for item in results if item["status"] == "not_cached"),
    }
    return {"checked_at": _now(), "summary": summary, "results": results}


def repair_registry_cache(item_id: str | None = None) -> dict[str, Any]:
    check = check_registry_cache_integrity(item_id)
    repairable = [item for item in check["results"] if item["status"] in {"missing", "hash_mismatch", "size_mismatch", "not_cached"}]
    results = []
    for result in repairable:
        rid = result["registry_item_id"]
        try:
            updated = refresh_registry_cache(rid)
            append_registry_event(rid, "cache_repaired", "system", before={}, after=updated, note=f"Cache repaired from status {result['status']}.")
            results.append({"registry_item_id": rid, "status": "repaired", "message": "Cache refreshed."})
        except Exception as exc:
            append_registry_event(rid, "cache_repair_failed", "system", before={}, after={}, note=str(exc))
            results.append({"registry_item_id": rid, "status": "failed", "message": str(exc)})
    return {"repaired_at": _now(), "checked": check["summary"], "results": results}


def _check_item(item: dict[str, Any]) -> dict[str, Any]:
    path = Path(item.get("cached_file_path") or "")
    base = {
        "registry_item_id": item.get("id"),
        "part_number": item.get("part_number"),
        "expected_sha256": item.get("sha256", ""),
        "actual_sha256": "",
        "expected_size": item.get("file_size_bytes"),
        "actual_size": None,
    }
    if not item.get("cached_file_path"):
        return {**base, "status": "not_cached", "message": "No cached file path recorded."}
    if not path.exists():
        return {**base, "status": "missing", "message": "Cached file is missing."}
    actual_size = path.stat().st_size
    actual_sha = _sha256(path)
    base = {**base, "actual_sha256": actual_sha, "actual_size": actual_size}
    if item.get("sha256") and actual_sha != item.get("sha256"):
        return {**base, "status": "hash_mismatch", "message": "Cached file SHA256 differs from registry."}
    if item.get("file_size_bytes") is not None and actual_size != int(item.get("file_size_bytes") or 0):
        return {**base, "status": "size_mismatch", "message": "Cached file size differs from registry."}
    return {**base, "status": "ok", "message": "Cache integrity verified."}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
