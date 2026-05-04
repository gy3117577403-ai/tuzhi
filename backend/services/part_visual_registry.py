from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "part_visual_registry.json"


def _normalize_token(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", (value or "").upper())


def _load_registry() -> dict[str, Any]:
    if not _REGISTRY_PATH.exists():
        return {"items": []}
    return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))


def find_visual_item(
    text: str | None = None,
    manufacturer: str | None = None,
    part_number: str | None = None,
) -> dict[str, Any] | None:
    """
    Exact / alias hit on part_visual_registry.
    Returns full item dict or None.
    """
    data = _load_registry()
    items = data.get("items") or []
    if not items:
        return None

    text_n = _normalize_token(text or "")
    pn_in = _normalize_token(part_number or "")

    for item in items:
        ipn = _normalize_token(str(item.get("part_number", "")))
        if pn_in and ipn and pn_in == ipn:
            return dict(item)
        for alias in item.get("aliases") or []:
            an = _normalize_token(str(alias))
            if an and pn_in and an == pn_in:
                return dict(item)
        if text_n:
            if ipn and len(ipn) >= 4 and ipn in text_n:
                return dict(item)
            for alias in item.get("aliases") or []:
                an = _normalize_token(str(alias))
                if an and len(an) >= 4 and an in text_n:
                    return dict(item)
    return None
