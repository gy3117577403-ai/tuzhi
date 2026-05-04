from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from services.json_store import atomic_write_json, file_lock, read_json
from services.registry_store import DATA_ROOT
from services.audit_signature import sign_event, verify_event_signature

HISTORY_PATH = DATA_ROOT / "cad_registry_history.json"

KEY_FIELDS = [
    "id",
    "manufacturer",
    "part_number",
    "status",
    "revision",
    "version_label",
    "sha256",
    "file_size_bytes",
    "cache_status",
    "cached_at",
    "cached_file_path",
    "updated_at",
]


def append_registry_event(
    registry_item_id: str,
    event_type: str,
    actor: str = "system",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    note: str = "",
) -> dict[str, Any]:
    data = read_json(HISTORY_PATH, {"events": []})
    event = {
        "id": uuid.uuid4().hex,
        "registry_item_id": registry_item_id,
        "event_type": event_type,
        "actor": actor,
        "created_at": _now(),
        "before": _snapshot(before),
        "after": _snapshot(after),
        "note": note,
    }
    data.setdefault("events", []).append(sign_event(event))
    with file_lock(HISTORY_PATH):
        atomic_write_json(HISTORY_PATH, data)
    return event


def list_registry_events(registry_item_id: str | None = None, event_type: str | None = None) -> list[dict[str, Any]]:
    events = read_json(HISTORY_PATH, {"events": []}).get("events", [])
    if registry_item_id:
        events = [event for event in events if event.get("registry_item_id") == registry_item_id]
    if event_type:
        events = [event for event in events if event.get("event_type") == event_type]
    return sorted(events, key=lambda event: event.get("created_at", ""))


def get_registry_item_history(registry_item_id: str) -> dict[str, Any]:
    return {"events": list_registry_events(registry_item_id=registry_item_id)}


def verify_registry_history_signatures() -> dict[str, Any]:
    events = read_json(HISTORY_PATH, {"events": []}).get("events", [])
    results = [verify_event_signature(event) for event in events]
    summary = {
        "total_events": len(results),
        "valid": sum(1 for item in results if item["status"] == "valid"),
        "invalid": sum(1 for item in results if item["status"] == "invalid"),
        "unsigned_legacy": sum(1 for item in results if item["status"] == "unsigned_legacy"),
    }
    return {"verified_at": _now(), "summary": summary, "results": results}


def _snapshot(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    return {key: payload.get(key) for key in KEY_FIELDS if key in payload}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
