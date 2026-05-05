"""Rank image search hits toward likely connector product photography."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BACKEND_ROOT, ".env"), override=True)

TRUSTED_MANUFACTURERS = (
    "te.com",
    "molex.com",
    "amphenol.com",
    "phoenixcontact.com",
    "harting.com",
)
TRUSTED_DISTRIBUTORS = (
    "mouser.com",
    "mouser.cn",
    "digikey.com",
    "digikey.cn",
    "element14",
    "rs-online",
    "newark.com",
    "arrow.com",
    "ttiinc.com",
)
PRODUCT_TERMS = (
    "connector",
    "housing",
    "plug",
    "socket",
    "terminal",
    "automotive",
    "receptacle",
    "header",
)
BAD_IMAGE_TERMS = ("logo", "icon", "sprite", "banner", "ads", "advert", "placeholder")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
MAX_PROBE_BYTES = 15 * 1024 * 1024


def rank_connector_image_results(
    query: str,
    results: list[dict[str, Any]],
    max_results: int | None = None,
    enable_probing: bool | None = None,
) -> dict[str, Any]:
    if not results:
        return {
            "selected": None,
            "candidates": [],
            "selection_reason": "No image search results.",
            "confidence": "low",
            "needs_user_selection": True,
            "ranker": {"enabled": True, "strategy": "part_number_domain_image_quality"},
        }

    limit = max(1, min(24, int(max_results or len(results) or 8)))
    probing = _env_bool("IMAGE_SEARCH_ENABLE_CANDIDATE_PROBING", True) if enable_probing is None else enable_probing
    probe_limit = min(8, len(results)) if probing else 0
    scored: list[dict[str, Any]] = []

    for index, item in enumerate(results):
        row = dict(item)
        score, reasons = _score_candidate(query, row)
        if index < probe_limit:
            ok, probe_reason = _probe_image(row.get("image_url") or row.get("thumbnail_url") or "")
            row["image_probe_ok"] = ok
            if ok:
                score += 0.12
                reasons.append("image url available")
            else:
                score -= 0.22
                reasons.append(probe_reason or "image url unavailable")
        row["score"] = round(max(0.0, min(1.0, score)), 3)
        row["rank_reason"] = "; ".join(dict.fromkeys(reasons)) or "basic image result"
        scored.append(row)

    scored.sort(key=lambda item: (float(item.get("score") or 0), -int(item.get("rank") or 9999)), reverse=True)
    candidates = []
    for rank, row in enumerate(scored[:limit], 1):
        row = dict(row)
        row["rank"] = rank
        candidates.append(row)

    best = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    gap = float(best.get("score") or 0) - float(second.get("score") or 0) if second else 1.0
    confidence = "high" if float(best.get("score") or 0) >= 0.72 and gap >= 0.08 else "medium"
    if float(best.get("score") or 0) < 0.45:
        confidence = "low"
    needs_pick = gap < 0.08 or confidence != "high"

    return {
        "selected": best,
        "candidates": candidates,
        "selection_reason": best.get("rank_reason") or "highest ranked candidate",
        "confidence": confidence,
        "needs_user_selection": bool(needs_pick),
        "ranker": {"enabled": True, "strategy": "part_number_domain_image_quality"},
    }


def _score_candidate(query: str, item: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    title = str(item.get("title") or "")
    image_url = str(item.get("image_url") or "")
    source_url = str(item.get("source_url") or "")
    blob = " ".join([title, image_url, source_url]).lower()
    score = 0.18

    for part in _part_numbers(query):
        part_l = part.lower()
        compact = _compact(part)
        if part_l and part_l in blob:
            score += 0.28
            reasons.append("part number match")
            break
        if compact and compact in _compact(blob):
            score += 0.14
            reasons.append("weak part number match")
            break

    domain = _domain(item)
    if _contains_any(domain, TRUSTED_MANUFACTURERS):
        score += 0.18
        reasons.append("trusted manufacturer domain")
    elif _contains_any(domain, TRUSTED_DISTRIBUTORS):
        score += 0.14
        reasons.append("trusted distributor domain")
    elif any(term in domain for term in ("connector", "electronic", "component", "distributor", "manufacturer")):
        score += 0.06
        reasons.append("connector-related domain")

    if _has_image_extension(image_url):
        score += 0.08
        reasons.append("image file extension")
    if _contains_any(blob, BAD_IMAGE_TERMS):
        score -= 0.22
        reasons.append("likely logo/icon/banner")

    width = _int_or_none(item.get("width"))
    height = _int_or_none(item.get("height"))
    if width and height:
        if width < 120 or height < 120:
            score -= 0.12
            reasons.append("small image dimensions")
        else:
            score += 0.08
            reasons.append("reasonable image dimensions")

    if _contains_any(blob, PRODUCT_TERMS):
        score += 0.12
        reasons.append("product-like connector terms")
    if ("datasheet" in blob or ".pdf" in blob) and not _has_image_extension(image_url):
        score -= 0.08
        reasons.append("datasheet/pdf candidate")

    try:
        original_rank = int(item.get("rank") or 999)
    except (TypeError, ValueError):
        original_rank = 999
    score += max(0.0, 0.1 - original_rank * 0.01)
    return score, reasons


def _probe_image(image_url: str) -> tuple[bool, str]:
    if not image_url:
        return False, "empty image url"
    if image_url.startswith("/api/test-assets/"):
        return True, "local test asset"
    if not image_url.startswith(("http://", "https://")):
        return False, "unsupported image url"
    try:
        timeout = max(2.0, min(20.0, float(os.getenv("IMAGE_SEARCH_TIMEOUT_SECONDS") or 8)))
    except ValueError:
        timeout = 8.0
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": "ConnectorCAD-MVP/1.0"}) as client:
            response = client.head(image_url)
            if response.status_code in (405, 501) or response.status_code >= 400:
                response = client.get(image_url, headers={"Range": "bytes=0-1024"})
            content_type = (response.headers.get("content-type") or "").split(";")[0].lower()
            length = _int_or_none(response.headers.get("content-length"))
            if response.status_code >= 400:
                return False, "image url returned error"
            if content_type and not content_type.startswith("image/"):
                return False, "content-type is not image"
            if length and length > MAX_PROBE_BYTES:
                return False, "image exceeds size limit"
            return True, "image url available"
    except Exception:
        return False, "image probe failed"


def _part_numbers(query: str) -> list[str]:
    text = query or ""
    matches = re.findall(r"[A-Za-z0-9]+(?:[-_.][A-Za-z0-9]+)+|[A-Z]{1,}[0-9][A-Z0-9-]{3,}", text, flags=re.I)
    return [m for m in matches if any(ch.isdigit() for ch in m)]


def _domain(item: dict[str, Any]) -> str:
    domain = str(item.get("domain") or "").lower()
    if domain:
        return domain
    for key in ("source_url", "image_url"):
        url = str(item.get(key) or "")
        if url:
            try:
                return urlparse(url).netloc.lower()
            except Exception:
                return ""
    return ""


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    low = (text or "").lower()
    return any(term in low for term in terms)


def _has_image_extension(url: str) -> bool:
    try:
        path = urlparse(url or "").path.lower()
    except Exception:
        path = (url or "").lower()
    return path.endswith(IMAGE_EXTENSIONS)


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
