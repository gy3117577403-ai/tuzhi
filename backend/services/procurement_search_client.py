from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from pathlib import Path

from dotenv import load_dotenv

from services.procurement_data_normalizer import normalize_offer_row, offer_matches_query
from services.procurement_importer import load_imported_offers
from services.procurement_models import ProcurementResult, ProcurementSearchRequest
from services.procurement_ranker import sort_procurement_results
from services.procurement_serpapi_provider import search_serpapi_procurement


BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env", override=True)


def _svg_data_url(color: str, shape: str = "rect") -> str:
    if shape == "round":
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 240"><rect width="360" height="240" fill="#f7f7f4"/><ellipse cx="176" cy="122" rx="82" ry="70" fill="{color}" stroke="#222" stroke-width="10"/><ellipse cx="176" cy="122" rx="34" ry="29" fill="#f1f1ef" stroke="#333" stroke-width="7"/><rect x="50" y="101" width="74" height="42" rx="14" fill="{color}" stroke="#222" stroke-width="8"/><text x="24" y="220" font-family="Arial" font-size="18" fill="#555">圆形连接器示意图</text></svg>"""
    else:
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 240"><rect width="360" height="240" fill="#f7f7f4"/><rect x="62" y="72" width="236" height="104" rx="18" fill="{color}" stroke="#222" stroke-width="8"/><rect x="96" y="99" width="168" height="52" rx="12" fill="#f5f5ef" stroke="#333" stroke-width="5"/><circle cx="126" cy="125" r="10" fill="#222"/><circle cx="162" cy="125" r="10" fill="#222"/><circle cx="198" cy="125" r="10" fill="#222"/><circle cx="234" cy="125" r="10" fill="#222"/><rect x="132" y="48" width="96" height="25" rx="7" fill="{color}" stroke="#222" stroke-width="6"/><text x="24" y="220" font-family="Arial" font-size="18" fill="#555">矩形连接器示意图</text></svg>"""
    from urllib.parse import quote

    return "data:image/svg+xml;utf8," + quote(svg)


def _item(
    *,
    id: str,
    platform: str,
    title: str,
    shop_name: str,
    price: float | None,
    price_type: str = "normal",
    shipping_location: str,
    stock_status: str,
    moq: int,
    key_parameters: dict[str, Any],
    match_score: float,
    risk_tags: list[str],
    product_url: str,
    image_url: str,
) -> ProcurementResult:
    tags = list(risk_tags)
    verification_status = "search_summary_only"
    if price is None or price_type == "unknown":
        price_type = "unknown"
        verification_status = "needs_confirmation"
        for tag in ("价格待确认", "需打开链接确认"):
            if tag not in tags:
                tags.append(tag)
    elif price_type == "normal":
        for tag in ("搜索摘要价", "需打开链接确认"):
            if tag not in tags:
                tags.append(tag)
    elif price_type == "abnormal":
        for tag in ("价格异常", "需人工确认", "需打开链接确认"):
            if tag not in tags:
                tags.append(tag)
    elif price_type in {"negotiable", "sample"}:
        verification_status = "needs_confirmation"
        for tag in ("价格待确认", "需打开链接确认"):
            if tag not in tags:
                tags.append(tag)
    return ProcurementResult(
        id=id,
        title=title,
        platform=platform,  # type: ignore[arg-type]
        shop_name=shop_name,
        price=price,
        currency="CNY",
        price_type=price_type,  # type: ignore[arg-type]
        price_verification_status=verification_status,  # type: ignore[arg-type]
        shipping_location=shipping_location,
        stock_status=stock_status,
        moq=moq,
        image_url=image_url,
        product_url=product_url,
        key_parameters=key_parameters,
        match_score=match_score,
        risk_tags=tags,
        updated_at=datetime.now(timezone.utc).isoformat(),
        source_type="mock",
        source_name="内置 mock 商品数据",
        data_freshness="mock",
    )


def mock_procurement_results(query: str) -> list[ProcurementResult]:
    part = (query or "1-968970-1").split()[0]
    return [
        _item(id="taobao-001", platform="淘宝", title=f"TE 同款 {part} 汽车连接器护套 4孔 蓝色", shop_name="华南接插件现货店", price=3.8, shipping_location="广东 深圳", stock_status="现货 1200 件", moq=10, key_parameters={"brand": "TE", "part_number": part, "positions": "4P", "color": "蓝色", "type": "汽车连接器"}, match_score=0.96, risk_tags=["完全匹配", "需核对原厂授权"], product_url="https://example.com/taobao/1-968970-1", image_url=_svg_data_url("#2f73d8")),
        _item(id="jd-001", platform="京东", title=f"{part} 连接器外壳 端子配套 汽车插件", shop_name="工控电子自营专区", price=6.5, shipping_location="江苏 苏州", stock_status="现货 380 件", moq=1, key_parameters={"brand": "TE 同款", "part_number": part, "positions": "4P", "color": "蓝色", "type": "线束外壳"}, match_score=0.92, risk_tags=["完全匹配", "价格含平台服务费"], product_url="https://example.com/jd/1-968970-1", image_url=_svg_data_url("#2f73d8")),
        _item(id="1688-001", platform="1688", title=f"汽车连接器 {part} 蓝色胶壳 可配端子", shop_name="东莞精密连接器厂", price=1.26, shipping_location="广东 东莞", stock_status="库存 9800 件", moq=500, key_parameters={"brand": "兼容料", "part_number": part, "positions": "4P", "color": "蓝色", "type": "批发胶壳"}, match_score=0.89, risk_tags=["完全匹配", "起订量较高"], product_url="https://example.com/1688/1-968970-1", image_url=_svg_data_url("#2f73d8")),
        _item(id="taobao-002", platform="淘宝", title="8-968970-1 相近型号蓝色汽车接插件", shop_name="线束端子配件仓", price=2.9, shipping_location="浙江 宁波", stock_status="现货 600 件", moq=20, key_parameters={"brand": "TE 同款", "part_number": "8-968970-1", "positions": "4P", "color": "蓝色", "type": "汽车插件"}, match_score=0.71, risk_tags=["相近型号风险", "不能直接替代需确认"], product_url="https://example.com/taobao/8-968970-1", image_url=_svg_data_url("#3777d4")),
        _item(id="other-001", platform="其他", title=f"TE Connectivity {part} 连接器采购代询", shop_name="Mouser 代购报价", price=12.4, shipping_location="海外仓", stock_status="预计 2-3 周", moq=1, key_parameters={"brand": "TE Connectivity", "part_number": part, "positions": "4P", "color": "蓝色", "type": "品牌渠道"}, match_score=0.94, risk_tags=["完全匹配", "交期不确定", "需核对含税运费"], product_url="https://example.com/distributor/1-968970-1", image_url=_svg_data_url("#2f73d8")),
        _item(id="1688-002", platform="1688", title="6-968970-1 相近规格连接器胶壳 批发", shop_name="温州端子连接器批发", price=0.18, price_type="abnormal", shipping_location="浙江 温州", stock_status="库存 20000 件", moq=1000, key_parameters={"brand": "未知", "part_number": "6-968970-1", "positions": "4P", "color": "蓝色", "type": "批发低价"}, match_score=0.63, risk_tags=["相近型号风险", "价格异常", "参数不完整"], product_url="https://example.com/1688/6-968970-1", image_url=_svg_data_url("#2f73d8")),
        _item(id="jd-002", platform="京东", title=f"{part} 蓝色连接器套装 含端子密封塞", shop_name="汽车线束配件旗舰店", price=9.9, shipping_location="上海", stock_status="现货 88 套", moq=1, key_parameters={"brand": "兼容套装", "part_number": part, "positions": "4P", "color": "蓝色", "type": "套装"}, match_score=0.88, risk_tags=["完全匹配", "套装价格不可直接对比单壳"], product_url="https://example.com/jd/kit-1-968970-1", image_url=_svg_data_url("#2f73d8")),
        _item(id="taobao-003", platform="淘宝", title="圆形防水连接器 4芯 黑色 航空插头", shop_name="工业圆形航空插头店", price=18.5, shipping_location="浙江 宁波", stock_status="现货 260 件", moq=2, key_parameters={"brand": "未知", "part_number": "非目标料号", "positions": "4芯", "color": "黑色", "type": "圆形防水连接器"}, match_score=0.42, risk_tags=["图片相似但型号不匹配", "非目标料号"], product_url="https://example.com/taobao/round-connector", image_url=_svg_data_url("#18191b", "round")),
        _item(id="other-002", platform="其他", title=f"{part} 授权渠道询价入口", shop_name="授权供应商询价", price=None, price_type="unknown", shipping_location="发货地待确认", stock_status="库存待确认", moq=1, key_parameters={"brand": "TE", "part_number": part, "positions": "4P", "color": "蓝色", "type": "询价入口"}, match_score=0.84, risk_tags=["完全匹配"], product_url="https://example.com/quote/1-968970-1", image_url=_svg_data_url("#2f73d8")),
    ]


def _generic_json_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("items", "results", "data", "offers"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def generic_json_results(query: str) -> list[ProcurementResult]:
    base_url = os.getenv("PROCUREMENT_GENERIC_JSON_BASE_URL", "").strip()
    if not base_url:
        return []
    api_key = os.getenv("PROCUREMENT_GENERIC_JSON_API_KEY", "").strip()
    auth_header = os.getenv("PROCUREMENT_GENERIC_JSON_AUTH_HEADER", "Authorization").strip() or "Authorization"
    separator = "&" if "?" in base_url else "?"
    url = f"{base_url}{separator}{urlencode({'q': query})}"
    headers = {"Accept": "application/json"}
    if api_key:
        headers[auth_header] = api_key if auth_header.lower() not in {"authorization"} else f"Bearer {api_key}"
    try:
        request = Request(url, headers=headers, method="GET")
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []

    offers: list[ProcurementResult] = []
    for index, row in enumerate(_generic_json_items(payload), start=1):
        offer, _warning = normalize_offer_row(
            row,
            row_index=index,
            source_id="generic-json",
            source_name="授权 generic_json 接口",
            source_type="generic_json",
            platform_label="其他",
            import_id=None,
            query_hint=query,
        )
        if offer:
            offers.append(offer)
    return offers


def search_procurement(request: ProcurementSearchRequest) -> list[ProcurementResult]:
    source_types = set(request.source_types or ["mock", "csv_upload", "excel_upload", "generic_json"])
    provider_results: list[ProcurementResult] = []
    if "mock" in source_types:
        provider_results.extend(mock_procurement_results(request.query))
    if "csv_upload" in source_types or "excel_upload" in source_types:
        provider_results.extend(item for item in load_imported_offers() if item.source_type in source_types)
    if "generic_json" in source_types:
        provider_results.extend(generic_json_results(request.query))

    allowed = set(request.platforms or ["淘宝", "京东", "1688", "其他"])
    filtered = [
        item
        for item in provider_results
        if item.platform in allowed and (item.source_type == "mock" or offer_matches_query(item, request.query))
    ]
    return sort_procurement_results(filtered, sort_by=request.sort_by, target_location=request.target_location)


def search_procurement_with_summary(request: ProcurementSearchRequest) -> tuple[list[ProcurementResult], dict[str, Any], list[str]]:
    provider = (os.getenv("PROCUREMENT_SEARCH_PROVIDER") or "").strip().lower()
    if not request.source_types and provider == "serpapi":
        serp_results, provider_summary, warnings = search_serpapi_procurement(request.query)
        if serp_results:
            allowed = set(request.platforms or ["淘宝", "京东", "1688", "其他"])
            filtered = [item for item in serp_results if item.platform in allowed]
            return sort_procurement_results(filtered, sort_by=request.sort_by, target_location=request.target_location), provider_summary, warnings
        provider_summary["provider_mode"] = "fallback"
        provider_summary["fallback_used"] = True
        warnings.append("真实搜索失败或无可用结果，当前展示模拟数据。")
        mock = mock_procurement_results(request.query)
        provider_summary["mock_count"] = len(mock)
        allowed = set(request.platforms or ["淘宝", "京东", "1688", "其他"])
        filtered = [item for item in mock if item.platform in allowed]
        return sort_procurement_results(filtered, sort_by=request.sort_by, target_location=request.target_location), provider_summary, warnings

    if not request.source_types:
        mock = mock_procurement_results(request.query)
        provider_summary = {
            "provider_mode": "mock",
            "serpapi_configured": False,
            "serpapi_shopping_count": 0,
            "serpapi_site_search_count": 0,
            "mock_count": len(mock),
            "fallback_used": True,
        }
        warnings = ["真实采购搜索未配置，当前为模拟数据。"]
        allowed = set(request.platforms or ["淘宝", "京东", "1688", "其他"])
        filtered = [item for item in mock if item.platform in allowed]
        return sort_procurement_results(filtered, sort_by=request.sort_by, target_location=request.target_location), provider_summary, warnings

    results = search_procurement(request)
    provider_summary = {
        "provider_mode": "mock",
        "serpapi_configured": False,
        "serpapi_shopping_count": 0,
        "serpapi_site_search_count": 0,
        "mock_count": len(results),
        "fallback_used": "mock" in set(request.source_types or []),
    }
    return results, provider_summary, []
