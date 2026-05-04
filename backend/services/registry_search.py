from __future__ import annotations

import math
from collections import Counter
from typing import Any

from services.registry_store import load_registry

SORT_FIELDS = {"updated_at", "created_at", "manufacturer", "part_number", "status", "source_category", "file_size_bytes"}


def search_registry_items(
    query: str | None = None,
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
    items = list(load_registry().get("items", []))
    filters = {
        "q": query,
        "status": status,
        "manufacturer": manufacturer,
        "part_number": part_number,
        "source_category": source_category,
        "cache_status": cache_status,
        "revision": revision,
    }
    if query:
        needle = query.lower()
        items = [
            item for item in items
            if needle in str(item.get("manufacturer", "")).lower()
            or needle in str(item.get("part_number", "")).lower()
            or needle in str(item.get("title", "")).lower()
        ]
    for key, expected in {
        "status": status,
        "manufacturer": manufacturer,
        "part_number": part_number,
        "source_category": source_category,
        "cache_status": cache_status,
        "revision": revision,
    }.items():
        if expected:
            items = [item for item in items if str(item.get(key, "")).lower() == str(expected).lower()]

    sort_by = sort_by if sort_by in SORT_FIELDS else "updated_at"
    reverse = sort_order.lower() != "asc"
    items = sorted(items, key=lambda item: _sort_value(item, sort_by), reverse=reverse)
    total = len(items)
    page_size = max(1, min(int(page_size or 20), 100))
    total_pages = max(1, math.ceil(total / page_size))
    page = max(1, min(int(page or 1), total_pages))
    start = (page - 1) * page_size
    return {
        "items": items[start:start + page_size],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "sort_by": sort_by,
        "sort_order": "desc" if reverse else "asc",
        "filters": filters,
    }


def get_registry_stats() -> dict[str, Any]:
    items = load_registry().get("items", [])
    by_status = Counter(item.get("status", "unknown") for item in items)
    by_source_category = Counter(item.get("source_category", "unknown") for item in items)
    by_cache_status = Counter(item.get("cache_status", "not_cached") or "not_cached" for item in items)
    return {
        "total_items": len(items),
        "by_status": _counter_payload(by_status, ["draft", "pending_review", "approved", "rejected", "deprecated", "failed_review"]),
        "by_source_category": _counter_payload(by_source_category, ["official_manufacturer", "authorized_distributor", "third_party_repository", "local_test", "unknown"]),
        "by_cache_status": _counter_payload(by_cache_status, ["cached", "missing", "invalid", "not_cached"]),
        "total_cached_bytes": sum(int(item.get("file_size_bytes") or 0) for item in items if item.get("cache_status") == "cached"),
        "approved_count": by_status.get("approved", 0),
        "pending_review_count": by_status.get("pending_review", 0),
        "deprecated_count": by_status.get("deprecated", 0),
    }


def _sort_value(item: dict[str, Any], key: str) -> Any:
    if key == "file_size_bytes":
        return int(item.get(key) or 0)
    return str(item.get(key, "") or "")


def _counter_payload(counter: Counter, keys: list[str]) -> dict[str, int]:
    return {key: counter.get(key, 0) for key in keys}
