"""Connector image search via configurable providers (mock / Bing-style REST — MVP scaffold).

Images Search API keys MUST come from environment variables only.
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BACKEND_ROOT, ".env"))

QUERY_BOOST_TERMS = ("connector", "datasheet", "housing", "CAD", "manufacturer")


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _safe_mode() -> bool:
    return _env("IMAGE_SEARCH_SAFE_MODE", "true").lower() in ("1", "true", "yes")


def _max_results(default: int = 8) -> int:
    try:
        return max(1, min(24, int(_env("IMAGE_SEARCH_MAX_RESULTS", str(default)) or default)))
    except ValueError:
        return default


def expand_connector_search_query(user_query: str) -> str:
    """Attach neutral search boosts so web indexes surface product photos."""
    q = (user_query or "").strip()
    if not q:
        return "connector " + " ".join(QUERY_BOOST_TERMS[:3])
    boost = " ".join(t for t in QUERY_BOOST_TERMS if t.lower() not in q.lower())
    return f"{q} {boost}".strip()


def _normalize_results(raw: list[dict[str, Any]], provider: str, query: str, base_rank: int = 1) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        title = str(item.get("title") or "")[:500]
        img = str(item.get("image_url") or item.get("thumbnail_url") or "").strip()
        thumb = str(item.get("thumbnail_url") or img).strip()
        src_page = str(item.get("source_url") or item.get("host_page_url") or "").strip()
        dom = ""
        if src_page:
            try:
                dom = urlparse(src_page).netloc.lower()
            except Exception:
                dom = ""
        out.append(
            {
                "title": title,
                "image_url": img or thumb,
                "thumbnail_url": thumb or img,
                "source_url": src_page,
                "domain": dom,
                "width": item.get("width"),
                "height": item.get("height"),
                "rank": base_rank + i,
            }
        )
    return out


def _bing_like_search(query: str, max_results: int) -> dict[str, Any]:
    """Placeholder for Bing / SerpAPI / Google PSE style endpoints."""
    base = _env("IMAGE_SEARCH_BASE_URL").rstrip("/")
    key = _env("IMAGE_SEARCH_API_KEY")
    if not base or not key:
        return {"status": "not_configured", "results": [], "warnings": ["IMAGE_SEARCH_BASE_URL or IMAGE_SEARCH_API_KEY missing"]}

    params = {"q": query, "count": max_results}
    headers = {"Ocp-Apim-Subscription-Key": key} if "bing" in base.lower() else {"Authorization": f"Bearer {key}"}
    try:
        with httpx.Client(timeout=45.0) as client:
            r = client.get(base, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        return {"status": "failed", "results": [], "warnings": [str(exc)]}

    items: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for entry in data.get("value") or data.get("images") or data.get("organic_results") or []:
            if isinstance(entry, dict):
                content = entry.get("thumbnail") or entry
                img_url = (
                    entry.get("contentUrl")
                    or entry.get("link")
                    or content.get("url")
                    or entry.get("image")
                    or ""
                )
                page_url = entry.get("hostPageUrl") or entry.get("link") or ""
                title = entry.get("name") or entry.get("title") or ""
                items.append(
                    {
                        "title": title,
                        "image_url": str(img_url),
                        "thumbnail_url": str(content.get("url") if isinstance(content, dict) else img_url),
                        "source_url": str(page_url),
                    }
                )
    return {"status": "success" if items else "failed", "results": items[:max_results], "warnings": []}


def _mock_search(query: str, max_results: int) -> dict[str, Any]:
    """Deterministic fake hits for integration tests (no external API)."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", query)[:40].strip("-") or "connector"
    results: list[dict[str, Any]] = []
    for i in range(min(max_results, 3)):
        results.append(
            {
                "title": f"[mock] connector product photo {i + 1} — {slug}",
                "image_url": f"https://picsum.photos/seed/{slug}-{i}/640/480",
                "thumbnail_url": f"https://picsum.photos/seed/{slug}-t{i}/120/120",
                "source_url": f"https://example.com/mock-product/{slug}/{i}",
                "width": 640,
                "height": 480,
            }
        )
    return {"status": "success", "results": results, "warnings": ["mock provider: results are placeholders"]}


def search_connector_images(query: str, max_results: int | None = None) -> dict[str, Any]:
    """
    Search product images for a connector query.

    Returns:
      query, provider, status (success|not_configured|failed), results[], warnings[]
    """
    mr = max_results if max_results is not None else _max_results()
    expanded = expand_connector_search_query(query)
    provider = _env("IMAGE_SEARCH_PROVIDER").lower() or ""

    warnings: list[str] = []

    if not provider or provider in ("none", "off", "disabled"):
        return {
            "query": expanded,
            "provider": "none",
            "status": "not_configured",
            "results": [],
            "warnings": ["IMAGE_SEARCH_PROVIDER not set — configure API or pass a manual image URL."],
        }

    if provider == "mock":
        pack = _mock_search(expanded, mr)
        pack["query"] = expanded
        pack["provider"] = "mock"
        return pack

    if provider == "manual":
        return {
            "query": expanded,
            "provider": "manual",
            "status": "not_configured",
            "results": [],
            "warnings": ["manual provider: supply selected_image_url in API body; no server-side search."],
        }

    if provider in ("bing", "serpapi", "google_cse", "custom"):
        pack = _bing_like_search(expanded, mr)
        pack["query"] = expanded
        pack["provider"] = provider
        if pack.get("status") != "success":
            pack.setdefault("warnings", []).extend(warnings)
        else:
            pack["results"] = _normalize_results(pack.get("results") or [], provider, expanded)
        return pack

    warnings.append(f"Unknown IMAGE_SEARCH_PROVIDER={provider!r}")
    return {
        "query": expanded,
        "provider": provider,
        "status": "not_configured",
        "results": [],
        "warnings": warnings,
    }
