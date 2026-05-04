from __future__ import annotations

import re
from typing import Any

CATEGORY_RANK = {
    "official_manufacturer": 0,
    "authorized_distributor": 1,
    "local_test": 2,
    "third_party_repository": 3,
    "unknown": 4,
}


def select_best_registry_item(
    items: list[dict[str, Any]],
    preferred_revision: str | None = None,
    preferred_version_label: str | None = None,
) -> dict[str, Any]:
    approved = [item for item in items if item.get("status") == "approved"]
    available_versions = [_version_summary(item) for item in items]
    if not approved:
        return {"selected_item": None, "selection_reason": "No approved registry item available.", "available_versions": available_versions}

    if preferred_revision:
        matches = [item for item in approved if str(item.get("revision", "")).lower() == preferred_revision.lower()]
        if matches:
            return {
                "selected_item": _latest(matches),
                "selection_reason": f"preferred_revision matched: {preferred_revision}",
                "available_versions": available_versions,
            }

    if preferred_version_label:
        matches = [item for item in approved if str(item.get("version_label", "")).lower() == preferred_version_label.lower()]
        if matches:
            return {
                "selected_item": _latest(matches),
                "selection_reason": f"preferred_version_label matched: {preferred_version_label}",
                "available_versions": available_versions,
            }

    selected = sorted(
        approved,
        key=lambda item: (
            -CATEGORY_RANK.get(item.get("source_category", "unknown"), 9),
            _revision_score(item.get("revision")),
            item.get("updated_at", ""),
        ),
        reverse=True,
    )[0]
    return {
        "selected_item": selected,
        "selection_reason": "Selected best approved source by source category, revision, and updated_at.",
        "available_versions": available_versions,
    }


def _latest(items: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(items, key=lambda item: (_revision_score(item.get("revision")), item.get("updated_at", "")), reverse=True)[0]


def _revision_score(revision: str | None) -> tuple[int, str]:
    value = str(revision or "").strip().upper()
    if not value or value == "UNKNOWN":
        return (0, "")
    if value.isdigit():
        return (int(value), value)
    letters = re.sub(r"[^A-Z]", "", value)
    if letters:
        score = 0
        for char in letters:
            score = score * 26 + (ord(char) - 64)
        return (score, value)
    return (0, value)


def _version_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "registry_item_id": item.get("id"),
        "revision": item.get("revision"),
        "version_label": item.get("version_label"),
        "status": item.get("status"),
        "source_category": item.get("source_category"),
        "updated_at": item.get("updated_at"),
    }
