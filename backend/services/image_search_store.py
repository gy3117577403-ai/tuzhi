from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from services.file_store import OUTPUTS_ROOT

SEARCH_ROOT = OUTPUTS_ROOT / "searches"


def create_search_record(
    query: str,
    provider: str,
    status: str,
    results: list[dict[str, Any]],
    warnings: list[str],
    expanded_query: str = "",
    ranker: dict[str, Any] | None = None,
) -> dict[str, Any]:
    search_id = uuid.uuid4().hex
    normalized = [_candidate_payload(item, index + 1, search_id) for index, item in enumerate(results)]
    record = {
        "search_id": search_id,
        "query": query,
        "expanded_query": expanded_query or query,
        "provider": provider,
        "status": status,
        "results": normalized,
        "warnings": warnings,
        "ranker": ranker or {"enabled": True, "strategy": "part_number_domain_image_quality"},
        "created_at": _now(),
    }
    save_search_results_json(record)
    return record


def get_search_record(search_id: str) -> dict[str, Any]:
    path = _record_path(search_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image search record not found")
    return json.loads(path.read_text(encoding="utf-8"))


def save_search_results_json(record: dict[str, Any]) -> Path:
    path = _record_path(record["search_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def resolve_candidate(search_id: str, candidate_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    record = get_search_record(search_id)
    for item in record.get("results", []):
        if item.get("id") == candidate_id:
            return record, item
    raise HTTPException(status_code=404, detail="Image search candidate not found")


def _candidate_payload(item: dict[str, Any], rank: int, search_id: str) -> dict[str, Any]:
    stable = "|".join([search_id, str(rank), str(item.get("image_url") or item.get("thumbnail_url") or ""), str(item.get("source_url") or "")])
    cid = "candidate_" + hashlib.sha1(stable.encode("utf-8")).hexdigest()[:12]
    return {
        "id": cid,
        "rank": item.get("rank") or rank,
        "title": item.get("title") or "",
        "image_url": item.get("image_url") or item.get("thumbnail_url") or "",
        "thumbnail_url": item.get("thumbnail_url") or item.get("image_url") or "",
        "source_url": item.get("source_url") or "",
        "domain": item.get("domain") or "",
        "width": item.get("width"),
        "height": item.get("height"),
        "score": item.get("score", max(0.1, round(1.0 - (rank - 1) * 0.08, 3))),
        "rank_reason": item.get("rank_reason") or "title/source appears connector-related",
        "provider": item.get("provider") or "",
        "provider_raw": item.get("provider_raw") or {},
        "image_probe_ok": item.get("image_probe_ok"),
    }


def _record_path(search_id: str) -> Path:
    if len(search_id) != 32 or any(ch not in "0123456789abcdef" for ch in search_id):
        raise HTTPException(status_code=400, detail="Invalid search_id")
    return SEARCH_ROOT / search_id / "image_search_results.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
