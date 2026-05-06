from __future__ import annotations

import uuid
from collections import Counter

from fastapi import HTTPException

from services.procurement_models import ProcurementSearchRecord, ProcurementSearchRequest, ProcurementSummary
from services.procurement_search_client import search_procurement_with_summary


_SEARCHES: dict[str, ProcurementSearchRecord] = {}


def create_procurement_search(request: ProcurementSearchRequest) -> ProcurementSearchRecord:
    results, provider_summary, provider_warnings = search_procurement_with_summary(request)
    normal_prices = [item.price for item in results if item.price_type == "normal" and item.price is not None]
    platform_counts = dict(Counter(item.platform for item in results))
    recommended_count = sum(
        1
        for item in results
        if item.match_score >= 0.85 and item.price_type != "abnormal" and not any("相近" in tag for tag in item.risk_tags)
    )
    record = ProcurementSearchRecord(
        search_id=uuid.uuid4().hex,
        query=request.query,
        target_location=request.target_location,
        status="success",
        results=results,
        summary=ProcurementSummary(
            total=len(results),
            platform_counts=platform_counts,
            lowest_price=min(normal_prices) if normal_prices else None,
            recommended_count=recommended_count,
            provider_summary=provider_summary,
        ),
        warnings=[
            *provider_warnings,
            "价格、库存、发货地均来自搜索摘要或授权数据源，需打开商品链接确认。",
            "系统不访问平台详情页，不绕过登录、验证码、风控或反爬限制。",
        ],
        provider=str(provider_summary.get("provider_mode") or "mock"),
        sort_by=request.sort_by,
        image_search_enabled=request.image_search_enabled,
    )
    _SEARCHES[record.search_id] = record
    return record


def get_procurement_search(search_id: str) -> ProcurementSearchRecord:
    record = _SEARCHES.get(search_id)
    if not record:
        raise HTTPException(status_code=404, detail="procurement search not found")
    return record
