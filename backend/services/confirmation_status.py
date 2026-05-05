from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_STATUSES = {"pending", "confirmed", "rejected", "not_applicable"}
VALID_ROLES = {"engineering", "process", "quality"}


def load_confirmation_checklist(output_dir: str | Path) -> dict[str, Any]:
    path = Path(output_dir) / "engineering_confirmation_checklist.json"
    if not path.exists():
        raise FileNotFoundError("engineering_confirmation_checklist.json not found")
    return json.loads(path.read_text(encoding="utf-8"))


def load_confirmation_status(output_dir: str | Path) -> dict[str, Any]:
    path = Path(output_dir) / "confirmation_status.json"
    if not path.exists():
        return initialize_confirmation_status(output_dir)
    return json.loads(path.read_text(encoding="utf-8"))


def initialize_confirmation_status(output_dir: str | Path) -> dict[str, Any]:
    out = Path(output_dir)
    checklist = load_confirmation_checklist(out)
    now = _now()
    job_id = out.name
    items = []
    for item in checklist.get("items", []):
        items.append(
            {
                "id": item.get("id", ""),
                "category": item.get("category", ""),
                "label": item.get("label", ""),
                "required": bool(item.get("required", True)),
                "risk_level": item.get("risk_level", "medium"),
                "basis": item.get("basis", ""),
                "status": "pending",
                "note": "",
                "confirmed_by": "",
                "role": "",
                "confirmed_at": "",
                "history": [],
            }
        )
    payload = {
        "status_type": "engineering_confirmation_status",
        "job_id": job_id,
        "created_at": now,
        "updated_at": now,
        "overall_status": "pending",
        "can_release_to_shopfloor": False,
        "can_enter_release_workflow": False,
        "release_condition": "Requires company approval before shopfloor release.",
        "items": items,
        "summary": {},
        "warnings": ["All required items must be confirmed before internal release."],
    }
    payload["summary"] = _summary(items)
    _write(out, payload)
    return payload


def update_confirmation_item(
    output_dir: str | Path,
    item_id: str,
    status: str,
    note: str,
    confirmed_by: str,
    role: str,
) -> dict[str, Any]:
    status = (status or "").strip()
    role = (role or "").strip()
    note = (note or "").strip()
    confirmed_by = (confirmed_by or "").strip()
    if status not in VALID_STATUSES:
        raise ValueError("Invalid confirmation status")
    if status != "pending":
        if role not in VALID_ROLES:
            raise ValueError("Invalid role")
        if not confirmed_by:
            raise ValueError("confirmed_by is required")
    if status == "rejected" and not note:
        raise ValueError("note is required when rejecting an item")

    payload = load_confirmation_status(output_dir)
    now = _now()
    found = False
    for item in payload.get("items", []):
        if item.get("id") != item_id:
            continue
        found = True
        item["status"] = status
        item["note"] = note
        item["confirmed_by"] = "" if status == "pending" else confirmed_by
        item["role"] = "" if status == "pending" else role
        item["confirmed_at"] = "" if status == "pending" else now
        item.setdefault("history", []).append(
            {
                "status": status,
                "note": note,
                "confirmed_by": item["confirmed_by"],
                "role": item["role"],
                "timestamp": now,
            }
        )
        break
    if not found:
        raise KeyError("Unknown confirmation item")

    payload["updated_at"] = now
    _apply_overall(payload)
    _write(output_dir, payload)
    return payload


def reset_confirmation_status(output_dir: str | Path) -> dict[str, Any]:
    out = Path(output_dir)
    path = out / "confirmation_status.json"
    if path.exists():
        backup = out / f"confirmation_status_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.bak.json"
        shutil.copyfile(path, backup)
        path.unlink()
    return initialize_confirmation_status(out)


def get_confirmation_summary(output_dir: str | Path) -> dict[str, Any]:
    return load_confirmation_status(output_dir).get("summary") or {}


def _apply_overall(payload: dict[str, Any]) -> None:
    items = payload.get("items", [])
    payload["summary"] = _summary(items)
    summary = payload["summary"]
    if summary["rejected_count"] > 0:
        overall = "rejected"
    elif summary["required_remaining_count"] == 0:
        overall = "ready_for_internal_release"
    elif summary["confirmed_count"] > 0 or summary["not_applicable_count"] > 0:
        overall = "partially_confirmed"
    else:
        overall = "pending"
    payload["overall_status"] = overall
    payload["can_release_to_shopfloor"] = False
    payload["can_enter_release_workflow"] = overall == "ready_for_internal_release"
    payload["release_condition"] = "Requires company approval before shopfloor release."
    if overall == "ready_for_internal_release":
        payload["warnings"] = ["Ready for internal release workflow only after company approval workflow."]
    elif overall == "rejected":
        payload["warnings"] = ["Rejected confirmation items block internal release workflow."]
    else:
        payload["warnings"] = ["All required items must be confirmed before internal release."]


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    required = [item for item in items if item.get("required")]
    resolved = {"confirmed", "not_applicable"}
    return {
        "required_count": len(required),
        "confirmed_count": sum(1 for item in items if item.get("status") == "confirmed"),
        "not_applicable_count": sum(1 for item in items if item.get("status") == "not_applicable"),
        "rejected_count": sum(1 for item in items if item.get("status") == "rejected"),
        "pending_count": sum(1 for item in items if item.get("status") == "pending"),
        "high_risk_count": sum(1 for item in items if item.get("risk_level") == "high"),
        "required_remaining_count": sum(1 for item in required if item.get("status") not in resolved),
        "all_required_resolved": all(item.get("status") in resolved for item in required),
    }


def _write(output_dir: str | Path, payload: dict[str, Any]) -> None:
    Path(output_dir, "confirmation_status.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
