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
        score, reasons, part_match = _score_candidate(query, row)
        row["part_match"] = part_match
        if index < probe_limit:
            ok, probe_reason = _probe_image(row.get("image_url") or row.get("thumbnail_url") or "")
            row["image_probe_ok"] = ok
            if ok:
                score += 0.12
                reasons.append("image url available")
            else:
                score -= 0.22
                reasons.append(probe_reason or "image url unavailable")
        evidence = build_match_evidence(part_match.get("query_part_number") or query, row, part_match)
        row["match_evidence"] = evidence
        evidence_score = float(evidence.get("evidence_score") or 0)
        evidence_level = evidence.get("evidence_level")
        if part_match.get("match_level") == "exact":
            if evidence_level == "high":
                score += 0.12
                reasons.append("high part evidence")
            elif evidence_level == "medium":
                score += 0.04
                reasons.append("medium part evidence")
            elif evidence_level == "low":
                score -= 0.16
                reasons.append("low part evidence")
        elif part_match.get("match_level") == "weak" and evidence_score >= 0.65:
            score += 0.05
            reasons.append("strong weak-match evidence")
        row["score"] = round(max(0.0, min(1.0, score)), 3)
        row["rank_reason"] = "; ".join(dict.fromkeys(reasons)) or "basic image result"
        scored.append(row)

    scored.sort(
        key=lambda item: (
            _match_sort_weight((item.get("part_match") or {}).get("match_level")),
            float(item.get("score") or 0),
            -int(item.get("rank") or 9999),
        ),
        reverse=True,
    )
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


def _score_candidate(query: str, item: dict[str, Any]) -> tuple[float, list[str], dict[str, Any]]:
    reasons: list[str] = []
    title = str(item.get("title") or "")
    image_url = str(item.get("image_url") or "")
    source_url = str(item.get("source_url") or "")
    blob = " ".join([title, image_url, source_url]).lower()
    score = 0.18

    query_part = (extract_part_numbers(query) or _part_numbers(query) or [query.strip() or ""])[0]
    part_match = compare_part_number_match(query_part, blob)
    match_level = part_match.get("match_level")
    if match_level == "exact":
        score += 0.5
        reasons.append("exact part number match")
    elif match_level == "weak":
        score += 0.18
        reasons.append("weak part number match")
    elif match_level == "near_miss":
        matched = part_match.get("matched_part_number") or "similar part number"
        score -= 0.25
        reasons.append(f"near-miss part number: candidate appears to be {matched}")

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
    return score, reasons, part_match


def extract_part_numbers(text: str) -> list[str]:
    """Extract likely connector part numbers while avoiding ordinary prose."""
    source = str(text or "")
    candidates: list[str] = []
    patterns = (
        r"(?<![A-Za-z0-9])[A-Za-z0-9]+(?:[-_.][A-Za-z0-9]+){1,}(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])[A-Za-z0-9]+\s+[A-Za-z0-9]+\s+[A-Za-z0-9]+(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])[A-Z]{1,}[0-9][A-Z0-9-]{3,}(?![A-Za-z0-9])",
    )
    for pattern in patterns:
        for match in re.findall(pattern, source, flags=re.I):
            part = re.sub(r"\s+", " ", str(match).strip())
            normalized = normalize_part_number(part)
            if not normalized or not any(ch.isdigit() for ch in normalized):
                continue
            if len(normalized) < 5 or len(normalized) > 32:
                continue
            lowered = part.lower()
            if lowered.startswith(("http", "www.")) or lowered.endswith((".com", ".cn", ".net")):
                continue
            if part not in candidates:
                candidates.append(part)
    return candidates


def normalize_part_number(part: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(part or "").lower())


def compare_part_number_match(query_part: str, candidate_text: str) -> dict[str, Any]:
    query_raw = str(query_part or "").strip()
    normalized_query = normalize_part_number(query_raw)
    base = {
        "match_level": "none",
        "query_part_number": query_raw,
        "matched_part_number": "",
        "normalized_query": normalized_query,
        "normalized_matched": "",
        "reason": "No part number match detected.",
    }
    if not query_raw or not normalized_query:
        base["reason"] = "No query part number detected."
        return base

    text = str(candidate_text or "")
    query_tokens = _part_tokens(query_raw)
    exact_pattern = _flexible_part_pattern(query_tokens)
    if exact_pattern and re.search(exact_pattern, text, flags=re.I):
        return {
            **base,
            "match_level": "exact",
            "matched_part_number": query_raw,
            "normalized_matched": normalized_query,
            "reason": "Full part number appears in candidate text.",
        }

    extracted = extract_part_numbers(text)
    for part in extracted:
        normalized = normalize_part_number(part)
        if normalized == normalized_query:
            return {
                **base,
                "match_level": "exact",
                "matched_part_number": part,
                "normalized_matched": normalized,
                "reason": "Normalized part number matches exactly.",
            }

    for part in extracted:
        if _is_near_miss(query_tokens, _part_tokens(part)):
            return {
                **base,
                "match_level": "near_miss",
                "matched_part_number": part,
                "normalized_matched": normalize_part_number(part),
                "reason": "Different prefix part number detected.",
            }

    body = _query_body(query_tokens)
    tail = _query_tail(query_tokens)
    if tail and re.search(_flexible_part_pattern(tail), text, flags=re.I):
        return {
            **base,
            "match_level": "weak",
            "matched_part_number": "-".join(tail),
            "normalized_matched": normalize_part_number("-".join(tail)),
            "reason": "Candidate matches body and suffix but is missing the query prefix.",
        }
    if body and re.search(rf"(?<![A-Za-z0-9]){re.escape(body)}(?![A-Za-z0-9])", text, flags=re.I):
        return {
            **base,
            "match_level": "weak",
            "matched_part_number": body,
            "normalized_matched": normalize_part_number(body),
            "reason": "Candidate contains the main body number only.",
        }
    return base


def build_match_evidence(query_part: str, item: dict[str, Any], part_match: dict[str, Any]) -> dict[str, Any]:
    query_raw = str(query_part or "").strip()
    match_level = str(part_match.get("match_level") or "none")
    title = str(item.get("title") or "")
    source_url = str(item.get("source_url") or "")
    image_url = str(item.get("image_url") or "")
    thumbnail_url = str(item.get("thumbnail_url") or "")
    domain = _domain(item)
    domain_trusted = _is_trusted_domain(domain)
    download_probe_ok = item.get("image_probe_ok")
    title_has_exact = _field_has_exact(query_raw, title)
    source_url_has_exact = _field_has_exact(query_raw, source_url)
    image_url_has_exact = _field_has_exact(query_raw, image_url)
    thumbnail_url_has_exact = _field_has_exact(query_raw, thumbnail_url)
    reasons: list[str] = []
    warnings: list[str] = []
    score = 0.0

    for label, ok, points in (
        ("title", title_has_exact, 0.24),
        ("source_url", source_url_has_exact, 0.24),
        ("image_url", image_url_has_exact, 0.18),
        ("thumbnail_url", thumbnail_url_has_exact, 0.1),
    ):
        if ok:
            score += points
            reasons.append(f"{label} contains exact part number")
        else:
            reasons.append(f"{label} does not contain exact part number")

    if domain_trusted:
        score += 0.16
        reasons.append("domain is trusted manufacturer/distributor")
    else:
        warnings.append("Domain is not in the trusted manufacturer/distributor list.")

    if download_probe_ok is True:
        score += 0.16
        reasons.append("image URL probe succeeded")
    elif download_probe_ok is False:
        score -= 0.08
        warnings.append("Image URL probe failed or did not confirm an image.")

    if _looks_garbled(title):
        score -= 0.12
        warnings.append("Title text may be garbled; verify the source page manually.")

    if match_level == "exact" and not (image_url_has_exact or thumbnail_url_has_exact):
        warnings.append("Image URL does not include exact part number; verify selected image visually.")
    if match_level == "near_miss":
        score = min(score, 0.25)
        warnings.append("Candidate appears to be a similar but different part number.")
    elif match_level == "none":
        score = min(score, 0.2)

    score = round(max(0.0, min(1.0, score)), 3)
    has_any_part_evidence = title_has_exact or source_url_has_exact or image_url_has_exact or thumbnail_url_has_exact
    if match_level == "exact" and (title_has_exact or source_url_has_exact) and domain_trusted and download_probe_ok is True and score >= 0.75:
        level = "high"
    elif match_level in {"exact", "weak"} and has_any_part_evidence and score >= 0.45:
        level = "medium"
    elif has_any_part_evidence or match_level in {"exact", "weak", "near_miss"}:
        level = "low"
    else:
        level = "unknown"

    return {
        "evidence_level": level,
        "evidence_score": score,
        "title_has_exact": title_has_exact,
        "source_url_has_exact": source_url_has_exact,
        "image_url_has_exact": image_url_has_exact,
        "thumbnail_url_has_exact": thumbnail_url_has_exact,
        "domain_trusted": domain_trusted,
        "download_probe_ok": download_probe_ok,
        "reasons": reasons,
        "warnings": warnings,
    }


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


def _match_sort_weight(match_level: str | None) -> int:
    return {"exact": 3, "weak": 2, "none": 1, "near_miss": 0}.get(str(match_level or "none"), 1)


def _part_tokens(part: str) -> list[str]:
    return [token.lower() for token in re.split(r"[^A-Za-z0-9]+", str(part or "")) if token]


def _flexible_part_pattern(tokens: list[str]) -> str:
    if not tokens:
        return ""
    return r"(?<![A-Za-z0-9])" + r"[-_.\s]+".join(re.escape(token) for token in tokens) + r"(?![A-Za-z0-9])"


def _query_body(tokens: list[str]) -> str:
    if len(tokens) >= 3:
        return tokens[1]
    if len(tokens) >= 2:
        return tokens[0]
    return ""


def _query_tail(tokens: list[str]) -> list[str]:
    if len(tokens) >= 3:
        return tokens[1:]
    return []


def _is_near_miss(query_tokens: list[str], candidate_tokens: list[str]) -> bool:
    if len(query_tokens) < 3 or len(candidate_tokens) < 3:
        return False
    if normalize_part_number("-".join(query_tokens)) == normalize_part_number("-".join(candidate_tokens)):
        return False
    if candidate_tokens[1:] == query_tokens[1:] and candidate_tokens[0] != query_tokens[0]:
        return True
    query_body = query_tokens[1]
    candidate_body = candidate_tokens[1]
    same_suffix = candidate_tokens[-1] == query_tokens[-1]
    different_full_part = candidate_tokens != query_tokens
    return bool(same_suffix and different_full_part and _is_similar_numeric_body(query_body, candidate_body))


def _is_similar_numeric_body(left: str, right: str) -> bool:
    if not (left.isdigit() and right.isdigit()):
        return False
    if left == right:
        return True
    if len(left) != len(right):
        return False
    distance = sum(1 for a, b in zip(left, right) if a != b)
    return distance <= 1


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


def _is_trusted_domain(domain: str) -> bool:
    return _contains_any(domain, TRUSTED_MANUFACTURERS) or _contains_any(domain, TRUSTED_DISTRIBUTORS)


def _field_has_exact(query_part: str, text: str) -> bool:
    query_tokens = _part_tokens(query_part)
    if not query_tokens:
        return False
    pattern = _flexible_part_pattern(query_tokens)
    if pattern and re.search(pattern, str(text or ""), flags=re.I):
        return True
    return normalize_part_number(query_part) in normalize_part_number(text)


def _looks_garbled(text: str) -> bool:
    sample = str(text or "")
    if not sample:
        return False
    if "�" in sample or "Ð" in sample or "Ñ" in sample or "Â" in sample:
        return True
    non_ascii = sum(1 for ch in sample if ord(ch) > 127)
    return len(sample) > 24 and non_ascii / max(1, len(sample)) > 0.55


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
