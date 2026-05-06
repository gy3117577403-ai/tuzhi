from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from services.procurement_models import ProcurementResult


BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env", override=True)


def serpapi_configured() -> bool:
    return bool(_get_api_key())


def _get_api_key() -> str:
    return (os.getenv("PROCUREMENT_SERPAPI_API_KEY") or "").strip()


def _base_url() -> str:
    return (os.getenv("PROCUREMENT_SERPAPI_BASE_URL") or "https://serpapi.com/search.json").strip()


def _max_results() -> int:
    try:
        return max(1, min(20, int(os.getenv("PROCUREMENT_SERPAPI_MAX_RESULTS") or "12")))
    except ValueError:
        return 12


def _domains() -> list[str]:
    raw = os.getenv("PROCUREMENT_SITE_SEARCH_DOMAINS") or "taobao.com,jd.com,1688.com"
    return [item.strip() for item in raw.split(",") if item.strip()]


def _fetch(params: dict[str, str]) -> dict[str, Any]:
    params = dict(params)
    params["api_key"] = _get_api_key()
    url = f"{_base_url()}?{urlencode(params)}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "connector-procurement-search/1.0"})
    with urlopen(request, timeout=20) as response:
        import json

        return json.loads(response.read().decode("utf-8"))


def _parse_price(value: Any) -> tuple[float | None, str, str]:
    if value in (None, ""):
        return None, "unknown", "needs_confirmation"
    if isinstance(value, (int, float)):
        price = float(value)
    else:
        text = str(value)
        if any(word in text for word in ("面议", "询价", "暂无", "待确认")):
            return None, "unknown", "needs_confirmation"
        match = re.search(r"\d+(?:[,.]\d+)?", text.replace(",", ""))
        if not match:
            return None, "unknown", "needs_confirmation"
        price = float(match.group(0))
    if price <= 0.05 or price >= 9999:
        return price, "abnormal", "search_summary_only"
    return price, "normal", "search_summary_only"


def _platform_from_url(url: str) -> str:
    host = url.lower()
    if "taobao.com" in host or "tmall.com" in host:
        return "淘宝"
    if "jd.com" in host:
        return "京东"
    if "1688.com" in host:
        return "1688"
    return "其他"


def _risk_tags(price_type: str, shipping_location: str, stock_status: str, matched: bool) -> list[str]:
    tags = ["需打开链接确认"]
    if price_type == "normal":
        tags.append("搜索摘要价")
    elif price_type == "abnormal":
        tags.extend(["价格异常", "需人工确认"])
    else:
        tags.append("价格待确认")
    if shipping_location == "待确认":
        tags.append("发货地待确认")
    if stock_status == "待确认":
        tags.append("库存待确认")
    if matched:
        tags.append("型号疑似匹配")
    else:
        tags.append("需核对型号")
    return list(dict.fromkeys(tags))


def _match_score(query: str, title: str, link: str) -> float:
    q = (query or "").split()[0].lower()
    text = f"{title} {link}".lower()
    if q and q in text:
        return 0.9
    normalized_q = re.sub(r"[^a-z0-9]", "", q)
    normalized_text = re.sub(r"[^a-z0-9]", "", text)
    if normalized_q and normalized_q in normalized_text:
        return 0.82
    if any(token and token in text for token in q.split("-")):
        return 0.58
    return 0.42


def _offer_from_raw(raw: dict[str, Any], *, query: str, source_type: str, index: int) -> ProcurementResult | None:
    title = str(raw.get("title") or raw.get("name") or "").strip()
    link = str(raw.get("link") or raw.get("product_link") or raw.get("source") or "").strip()
    if not title and not link:
        return None
    price, price_type, price_status = _parse_price(raw.get("price") or raw.get("extracted_price"))
    image_url = str(raw.get("thumbnail") or raw.get("thumbnail_url") or raw.get("image") or "").strip()
    source = str(raw.get("source") or raw.get("seller") or raw.get("displayed_link") or "").strip()
    platform = _platform_from_url(link or source)
    shipping = str(raw.get("delivery") or raw.get("shipping") or raw.get("location") or "").strip() or "待确认"
    stock = str(raw.get("stock") or raw.get("availability") or "").strip() or "待确认"
    matched = _match_score(query, title, link) >= 0.82
    return ProcurementResult(
        id=f"{source_type}-{index}",
        title=title or link,
        platform=platform,  # type: ignore[arg-type]
        shop_name=source or platform,
        price=price,
        currency="CNY",
        price_type=price_type,  # type: ignore[arg-type]
        price_verification_status=price_status,  # type: ignore[arg-type]
        shipping_location=shipping,
        shipping_verification_status="needs_confirmation" if shipping == "待确认" else "search_summary_only",
        stock_status=stock,
        stock_verification_status="needs_confirmation" if stock == "待确认" else "search_summary_only",
        moq=1,
        image_url=image_url,
        product_url=link or "#",
        key_parameters={"part_number": query.split()[0] if query else "", "type": "连接器", "source": "SerpAPI 搜索摘要"},
        match_score=_match_score(query, title, link),
        risk_tags=_risk_tags(price_type, shipping, stock, matched),
        updated_at=datetime.now(timezone.utc).isoformat(),
        source_type=source_type,  # type: ignore[arg-type]
        source_name="SerpAPI 搜索摘要",
        source_compliance_note="搜索引擎摘要结果，未访问平台详情页。",
        requires_manual_open=True,
        data_freshness="live_api",
    )


def search_serpapi_procurement(query: str) -> tuple[list[ProcurementResult], dict[str, Any], list[str]]:
    summary = {
        "provider_mode": "serpapi",
        "serpapi_configured": serpapi_configured(),
        "serpapi_shopping_count": 0,
        "serpapi_site_search_count": 0,
        "mock_count": 0,
        "fallback_used": False,
    }
    warnings: list[str] = []
    if not serpapi_configured():
        summary["provider_mode"] = "mock"
        return [], summary, ["真实采购搜索未配置，当前为模拟数据。"]

    results: list[ProcurementResult] = []
    max_results = _max_results()
    common = {
        "engine": "google_shopping",
        "q": f"{query} connector",
        "location": os.getenv("PROCUREMENT_SERPAPI_LOCATION") or "China",
        "gl": os.getenv("PROCUREMENT_SERPAPI_GL") or "cn",
        "hl": os.getenv("PROCUREMENT_SERPAPI_HL") or "zh-cn",
    }
    if (os.getenv("PROCUREMENT_ENABLE_SERPAPI_SHOPPING") or "true").lower() == "true":
        try:
            payload = _fetch(common)
            shopping = payload.get("shopping_results") or []
            for index, item in enumerate(shopping[:max_results], start=1):
                offer = _offer_from_raw(item, query=query, source_type="serpapi_shopping_summary", index=index)
                if offer:
                    results.append(offer)
            summary["serpapi_shopping_count"] = len(results)
        except Exception as exc:
            warnings.append(f"SerpAPI shopping 搜索失败：{type(exc).__name__}")

    if (os.getenv("PROCUREMENT_ENABLE_SERPAPI_SITE_SEARCH") or "true").lower() == "true":
        site_count = 0
        for domain in _domains():
            try:
                payload = _fetch(
                    {
                        "engine": "google",
                        "q": f"{query} connector site:{domain}",
                        "location": os.getenv("PROCUREMENT_SERPAPI_LOCATION") or "China",
                        "gl": os.getenv("PROCUREMENT_SERPAPI_GL") or "cn",
                        "hl": os.getenv("PROCUREMENT_SERPAPI_HL") or "zh-cn",
                    }
                )
                for item in (payload.get("organic_results") or [])[: max(2, max_results // max(len(_domains()), 1))]:
                    offer = _offer_from_raw(item, query=query, source_type="serpapi_site_search_summary", index=len(results) + 1)
                    if offer:
                        results.append(offer)
                        site_count += 1
            except Exception as exc:
                warnings.append(f"SerpAPI site:{domain} 搜索失败：{type(exc).__name__}")
        summary["serpapi_site_search_count"] = site_count

    deduped: list[ProcurementResult] = []
    seen: set[str] = set()
    for item in results:
        key = (item.product_url or item.title).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:max_results], summary, warnings
