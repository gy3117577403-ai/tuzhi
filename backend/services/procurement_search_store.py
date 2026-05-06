from __future__ import annotations

import uuid
from collections import Counter

from fastapi import HTTPException

from services.procurement_models import ProcurementSearchRecord, ProcurementSearchRequest, ProcurementSummary
from services.procurement_search_client import search_procurement


_SEARCHES: dict[str, ProcurementSearchRecord] = {}


def create_procurement_search(request: ProcurementSearchRequest) -> ProcurementSearchRecord:
    results = search_procurement(request)
    normal_prices = [item.price for item in results if item.price_type != "abnormal"]
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
        ),
        warnings=[
            "当前为采购搜索结果聚合，需人工确认型号、供应商资质、库存和交期。",
            "系统仅支持 mock、手动导入报价表、官方开放平台、企业授权 API 或供应商授权接口，不做违规爬虫。",
        ],
        provider="mock+manual_import+generic_json",
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
