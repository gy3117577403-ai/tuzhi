"""Connector image search via configurable providers.

Image search API keys must come from environment variables only.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from services.search_result_ranker import rank_connector_image_results

BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env", override=True)

BOOST_TERMS = ("connector", "housing")
CONNECTOR_TERMS = ("connector", "housing", "terminal", "plug", "socket", "receptacle", "header")


def search_connector_images(query: str, max_results: int | None = None, provider_override: str | None = None) -> dict[str, Any]:
    original_query = (query or "").strip()
    expanded = expand_connector_search_query(original_query)
    provider = (provider_override or _env("IMAGE_SEARCH_PROVIDER")).lower().strip()
    limit = _coerce_max_results(max_results)

    if not provider or provider in {"none", "off", "disabled"}:
        return _pack(original_query, expanded, "not_configured", "not_configured", [], ["IMAGE_SEARCH_PROVIDER not set."])
    if provider == "manual":
        provider = "manual_url"

    if provider == "mock":
        pack = _mock_search(original_query, expanded, limit)
    elif provider == "serpapi":
        pack = _serpapi_search(original_query, expanded, limit)
    elif provider == "bing":
        pack = _bing_search(original_query, expanded, limit)
    elif provider == "generic_json":
        pack = _generic_json_search(original_query, expanded, limit)
    elif provider == "manual_url":
        pack = _pack(
            original_query,
            expanded,
            "manual_url",
            "not_configured",
            [],
            ["manual_url provider does not search; use /api/connector-cad/jobs/from-manual-image-url."],
        )
    else:
        pack = _pack(original_query, expanded, provider, "not_configured", [], [f"Unknown IMAGE_SEARCH_PROVIDER={provider!r}."])

    if pack.get("status") == "success" and pack.get("results"):
        ranked = rank_connector_image_results(expanded, pack.get("results") or [], max_results=limit)
        pack["results"] = ranked.get("candidates") or []
        pack["ranker"] = ranked.get("ranker") or {"enabled": True, "strategy": "part_number_domain_image_quality"}
    else:
        pack["ranker"] = {"enabled": True, "strategy": "part_number_domain_image_quality"}
    return pack


def expand_connector_search_query(user_query: str) -> str:
    q = (user_query or "").strip()
    if not q:
        return "connector housing"
    lower = q.lower()
    additions = [term for term in BOOST_TERMS if term not in lower]
    if not any(term in lower for term in CONNECTOR_TERMS) and "terminal" not in lower:
        additions = ["connector", "housing"]
    return " ".join([q, *additions]).strip()


def _mock_search(original_query: str, expanded_query: str, max_results: int) -> dict[str, Any]:
    asset = BACKEND_ROOT / "test_assets" / "connector_reference_1_968970_1.png"
    if not asset.exists():
        return _pack(
            original_query,
            expanded_query,
            "mock",
            "not_configured",
            [],
            ["mock provider test asset missing: backend/test_assets/connector_reference_1_968970_1.png"],
        )
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", expanded_query)[:48].strip("-") or "connector"
    local_image = "http://127.0.0.1:8000/api/test-assets/connector_reference_1_968970_1.png"
    results: list[dict[str, Any]] = []
    for i in range(min(max_results, 3)):
        results.append(
            _candidate(
                provider="mock",
                rank=i + 1,
                title=f"[mock] connector product photo {i + 1} - {slug}",
                image_url=local_image,
                thumbnail_url=local_image,
                source_url=f"https://example.com/mock-product/{slug}/{i}",
                width=640,
                height=480,
                provider_raw={"mock": True, "asset": "connector_reference_1_968970_1.png"},
            )
        )
    return _pack(original_query, expanded_query, "mock", "success", results, ["mock provider: local deterministic test image"])


def _serpapi_search(original_query: str, expanded_query: str, max_results: int) -> dict[str, Any]:
    key = _env("IMAGE_SEARCH_API_KEY")
    if not key:
        return _pack(original_query, expanded_query, "serpapi", "not_configured", [], ["IMAGE_SEARCH_API_KEY missing for serpapi."])
    base = _env("IMAGE_SEARCH_BASE_URL") or _env("IMAGE_SEARCH_ENDPOINT") or "https://serpapi.com/search.json"
    params = {
        "engine": "google_images",
        "q": expanded_query,
        "api_key": key,
        "num": max_results,
        "ijn": 0,
    }
    if _env("IMAGE_SEARCH_MARKET"):
        params["gl"] = _market_to_gl(_env("IMAGE_SEARCH_MARKET"))
    data, warnings = _get_json(base, params=params, headers={})
    if data is None:
        return _pack(original_query, expanded_query, "serpapi", "failed", [], warnings)
    items = _extract_items(data, ("images_results", "image_results", "organic_results", "results", "items", "value"))
    if not items:
        warnings.append("No image result list found in serpapi response.")
    results = [
        _candidate(
            provider="serpapi",
            rank=i + 1,
            title=_str(item.get("title") or item.get("name")),
            image_url=_str(item.get("original") or item.get("image_url") or item.get("link") or item.get("url")),
            thumbnail_url=_str(item.get("thumbnail") or item.get("thumbnail_url") or item.get("thumbnailUrl")),
            source_url=_str(item.get("source") or item.get("source_url") or item.get("link") or item.get("page")),
            width=item.get("image_width") or item.get("width"),
            height=item.get("image_height") or item.get("height"),
            provider_raw=_safe_raw(item),
        )
        for i, item in enumerate(items[: max_results * 2])
        if isinstance(item, dict)
    ]
    results = [item for item in results if item.get("image_url") or item.get("thumbnail_url")]
    return _pack(original_query, expanded_query, "serpapi", "success" if results else "failed", results[:max_results], warnings)


def _bing_search(original_query: str, expanded_query: str, max_results: int) -> dict[str, Any]:
    key = _env("IMAGE_SEARCH_API_KEY")
    base = _env("IMAGE_SEARCH_BASE_URL") or _env("IMAGE_SEARCH_ENDPOINT")
    if not key or not base:
        return _pack(original_query, expanded_query, "bing", "not_configured", [], ["IMAGE_SEARCH_API_KEY or IMAGE_SEARCH_BASE_URL missing for bing."])
    headers = {"Ocp-Apim-Subscription-Key": key}
    params = {"q": expanded_query, "count": max_results, "safeSearch": "Strict" if _safe_mode() else "Moderate"}
    market = _env("IMAGE_SEARCH_MARKET")
    if market:
        params["mkt"] = market
    data, warnings = _get_json(base, params=params, headers=headers)
    if data is None:
        return _pack(original_query, expanded_query, "bing", "failed", [], warnings)
    items = _extract_items(data, ("value", "images", "results", "items"))
    if not items:
        warnings.append("No image result list found in bing response.")
    results = [
        _candidate(
            provider="bing",
            rank=i + 1,
            title=_str(item.get("name") or item.get("title")),
            image_url=_str(item.get("contentUrl") or item.get("image_url") or item.get("url")),
            thumbnail_url=_str(item.get("thumbnailUrl") or _thumbnail_value(item.get("thumbnail"))),
            source_url=_str(item.get("hostPageUrl") or item.get("source_url") or item.get("link") or item.get("page")),
            width=item.get("width"),
            height=item.get("height"),
            provider_raw=_safe_raw(item),
        )
        for i, item in enumerate(items[: max_results * 2])
        if isinstance(item, dict)
    ]
    results = [item for item in results if item.get("image_url") or item.get("thumbnail_url")]
    return _pack(original_query, expanded_query, "bing", "success" if results else "failed", results[:max_results], warnings)


def _generic_json_search(original_query: str, expanded_query: str, max_results: int) -> dict[str, Any]:
    base = _env("IMAGE_SEARCH_ENDPOINT") or _env("IMAGE_SEARCH_BASE_URL")
    if not base:
        return _pack(original_query, expanded_query, "generic_json", "not_configured", [], ["IMAGE_SEARCH_ENDPOINT or IMAGE_SEARCH_BASE_URL missing for generic_json."])
    key = _env("IMAGE_SEARCH_API_KEY")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    params = {"q": expanded_query, "query": expanded_query, "count": max_results, "limit": max_results}
    data, warnings = _get_json(base, params=params, headers=headers)
    if data is None:
        return _pack(original_query, expanded_query, "generic_json", "failed", [], warnings)
    items = _extract_items(data, ("images", "results", "items", "value"))
    if not items:
        warnings.append("No image result list found in generic_json response.")
    results = []
    for i, item in enumerate(items[: max_results * 2]):
        if not isinstance(item, dict):
            continue
        results.append(
            _candidate(
                provider="generic_json",
                rank=i + 1,
                title=_str(item.get("title") or item.get("name")),
                image_url=_str(item.get("image_url") or item.get("url") or item.get("contentUrl") or item.get("original")),
                thumbnail_url=_str(item.get("thumbnail_url") or item.get("thumbnail") or item.get("thumbnailUrl")),
                source_url=_str(item.get("source_url") or item.get("link") or item.get("hostPageUrl") or item.get("page")),
                width=item.get("width"),
                height=item.get("height"),
                provider_raw=_safe_raw(item),
            )
        )
    results = [item for item in results if item.get("image_url") or item.get("thumbnail_url")]
    return _pack(original_query, expanded_query, "generic_json", "success" if results else "failed", results[:max_results], warnings)


def _get_json(base: str, params: dict[str, Any], headers: dict[str, str]) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    safe_headers = {key: value for key, value in headers.items() if value}
    try:
        with httpx.Client(timeout=_timeout(), follow_redirects=True, headers={"User-Agent": "ConnectorCAD-MVP/1.0", **safe_headers}) as client:
            response = client.get(base, params=params)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        warnings.append(f"Image search request failed: {exc}")
        return None, warnings
    if not isinstance(data, dict):
        warnings.append("Image search response was not a JSON object.")
        return None, warnings
    return data, warnings


def _extract_items(data: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    for value in data.values():
        if isinstance(value, dict):
            nested = _extract_items(value, keys)
            if nested:
                return nested
    return []


def _candidate(
    provider: str,
    rank: int,
    title: str,
    image_url: str,
    thumbnail_url: str,
    source_url: str,
    width: Any,
    height: Any,
    provider_raw: dict[str, Any],
) -> dict[str, Any]:
    img = (image_url or thumbnail_url or "").strip()
    thumb = (thumbnail_url or image_url or "").strip()
    source = (source_url or "").strip()
    return {
        "id": "",
        "rank": rank,
        "title": title[:500],
        "image_url": img,
        "thumbnail_url": thumb,
        "source_url": source,
        "domain": _domain(source or img),
        "width": _int_or_none(width),
        "height": _int_or_none(height),
        "score": 0.0,
        "rank_reason": "",
        "provider": provider,
        "provider_raw": provider_raw,
    }


def _pack(query: str, expanded_query: str, provider: str, status: str, results: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:
    return {
        "query": query,
        "expanded_query": expanded_query,
        "provider": provider,
        "status": status,
        "results": results,
        "warnings": warnings,
        "ranker": {"enabled": True, "strategy": "part_number_domain_image_quality"},
    }


def _safe_raw(item: dict[str, Any]) -> dict[str, Any]:
    blocked = {"api_key", "key", "authorization", "headers"}
    safe: dict[str, Any] = {}
    for key, value in item.items():
        if key.lower() in blocked:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, dict):
            safe[key] = {k: v for k, v in value.items() if isinstance(v, (str, int, float, bool)) and k.lower() not in blocked}
    return safe


def _thumbnail_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("url") or value.get("thumbnailUrl")
    return value


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _coerce_max_results(max_results: int | None) -> int:
    raw = max_results if max_results is not None else _env("IMAGE_SEARCH_MAX_RESULTS", "8")
    try:
        return max(1, min(24, int(raw)))
    except (TypeError, ValueError):
        return 8


def _timeout() -> float:
    try:
        return max(2.0, min(60.0, float(_env("IMAGE_SEARCH_TIMEOUT_SECONDS", "15"))))
    except ValueError:
        return 15.0


def _safe_mode() -> bool:
    return _env("IMAGE_SEARCH_SAFE_MODE", "true").lower() in {"1", "true", "yes", "on"}


def _market_to_gl(market: str) -> str:
    return (market.split("-")[-1] if "-" in market else market or "cn").lower()


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _str(value: Any) -> str:
    return str(value or "").strip()


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None
