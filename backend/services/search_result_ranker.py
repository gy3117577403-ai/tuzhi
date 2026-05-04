"""Rank image search hits toward likely connector product photography."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

TIER_MANUFACTURER = {"te.com", "amphenol.com", "molex.com", "phoenixcontact.com", "harting.com"}
TIER_DISTRIBUTOR = {"mouser.com", "digikey.com", "arrow.com", "newark.com", "lcsc.com", "ttiinc.com"}
TIER_MARKETPLACE = {"alibaba.com", "amazon.", "ebay."}


def _tokens_from_query(query: str) -> set[str]:
    raw = re.sub(r"[^a-zA-Z0-9]+", " ", (query or "").lower()).split()
    return {t for t in raw if len(t) >= 2}


def _part_like_tokens(text: str) -> list[str]:
    return re.findall(r"[0-9]+(?:-[0-9A-Za-z]+)+|[A-Z]{2,}[0-9]{3,}[A-Z0-9-]*", text or "", flags=re.I)


def score_result(query: str, item: dict[str, Any]) -> float:
    score = 0.0
    q_tokens = _tokens_from_query(query)
    title = (item.get("title") or "").lower()
    src = (item.get("source_url") or "").lower()
    blob = f"{title} {src}"
    for tok in q_tokens:
        if tok in blob:
            score += 4.0
    for pn in _part_like_tokens(query):
        if pn.lower() in blob:
            score += 12.0

    domain = (item.get("domain") or "").lower()
    if not domain and src:
        try:
            domain = urlparse(src).netloc.lower()
        except Exception:
            domain = ""
    for tier in TIER_MANUFACTURER:
        if tier in domain:
            score += 8.0
            break
    for tier in TIER_DISTRIBUTOR:
        if tier in domain:
            score += 5.0
            break
    for tier in TIER_MARKETPLACE:
        if tier in domain:
            score -= 3.0

    img_url = item.get("image_url") or ""
    if any(img_url.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp")):
        score += 1.0
    if "logo" in title or "icon" in title:
        score -= 6.0
    if "datasheet" in title or "drawing" in title:
        score += 2.0

    try:
        rank_idx = int(item.get("rank") or 999)
    except (TypeError, ValueError):
        rank_idx = 999
    score += max(0.0, 5.0 - rank_idx * 0.15)

    return score


def verify_image_downloadable(image_url: str, timeout_sec: float = 8.0) -> bool:
    if not image_url or not image_url.startswith(("http://", "https://")):
        return False
    try:
        with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
            r = client.head(image_url)
            if r.status_code == 405 or r.status_code == 501:
                r = client.get(image_url, headers={"Range": "bytes=0-1024"})
            ct = (r.headers.get("content-type") or "").lower()
            return r.status_code < 400 and ("image" in ct or "octet-stream" in ct)
    except Exception:
        return False


def rank_connector_image_results(query: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Pick best candidate; attach scores and optional download probe.

    Returns:
      selected, candidates (sorted), selection_reason, confidence,
      needs_user_selection (bool)
    """
    if not results:
        return {
            "selected": None,
            "candidates": [],
            "selection_reason": "No image search results.",
            "confidence": "low",
            "needs_user_selection": True,
        }

    scored: list[tuple[float, dict[str, Any]]] = []
    for r in results:
        sc = score_result(query, r)
        scored.append((sc, dict(r)))

    scored.sort(key=lambda x: x[0], reverse=True)
    candidates_out: list[dict[str, Any]] = []
    for sc, row in scored[:12]:
        row = dict(row)
        row["_rank_score"] = round(sc, 3)
        ok_dl = verify_image_downloadable(str(row.get("image_url") or ""))
        row["_download_ok"] = ok_dl
        candidates_out.append(row)

    best = candidates_out[0]
    second = candidates_out[1] if len(candidates_out) > 1 else None
    gap = (best.get("_rank_score") or 0) - (second.get("_rank_score") or 0) if second else 99.0
    needs_pick = gap < 3.0 or not best.get("_download_ok")

    conf = "high"
    if needs_pick or not best.get("_download_ok"):
        conf = "medium" if gap >= 2.0 else "low"

    reason = f"Top score {best.get('_rank_score')} on title/domain overlap with query."
    if needs_pick:
        reason += " Scores are close or download uncertain — user should confirm reference image."

    return {
        "selected": best,
        "candidates": candidates_out,
        "selection_reason": reason,
        "confidence": conf,
        "needs_user_selection": bool(needs_pick),
    }
