from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.procurement_models import ProcurementResult, ProcurementSearchRequest
from services.procurement_ranker import sort_procurement_results


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
    price: float,
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
    return ProcurementResult(
        id=id,
        title=title,
        platform=platform,  # type: ignore[arg-type]
        shop_name=shop_name,
        price=price,
        currency="CNY",
        price_type=price_type,  # type: ignore[arg-type]
        shipping_location=shipping_location,
        stock_status=stock_status,
        moq=moq,
        image_url=image_url,
        product_url=product_url,
        key_parameters=key_parameters,
        match_score=match_score,
        risk_tags=risk_tags,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def mock_procurement_results(query: str) -> list[ProcurementResult]:
    part = (query or "1-968970-1").split()[0]
    return [
        _item(id="taobao-001", platform="淘宝", title=f"TE 同款 {part} 汽车连接器护套 4孔 蓝色", shop_name="华南接插件现货店", price=3.8, shipping_location="广东 深圳", stock_status="现货 1200 件", moq=10, key_parameters={"brand": "TE", "part_number": part, "positions": "4P", "color": "蓝色", "type": "汽车连接器"}, match_score=0.96, risk_tags=["完全匹配", "需核对原厂授权"], product_url="https://example.com/taobao/1-968970-1", image_url=_svg_data_url("#2f73d8")),
        _item(id="jd-001", platform="京东", title=f"{part} 连接器外壳 端子配套 汽车插件", shop_name="工控电子自营专区", price=6.5, shipping_location="江苏 苏州", stock_status="现货 380 件", moq=1, key_parameters={"brand": "TE 同款", "part_number": part, "positions": "4P", "color": "蓝色", "type": "线束外壳"}, match_score=0.92, risk_tags=["完全匹配", "价格含平台服务费"], product_url="https://example.com/jd/1-968970-1", image_url=_svg_data_url("#2f73d8")),
        _item(id="1688-001", platform="1688", title=f"汽车连接器 {part} 蓝色胶壳 可配端子", shop_name="东莞精密连接器厂", price=1.26, shipping_location="广东 东莞", stock_status="库存 9800 件", moq=500, key_parameters={"brand": "兼容料", "part_number": part, "positions": "4P", "color": "蓝色", "type": "批发胶壳"}, match_score=0.89, risk_tags=["完全匹配", "起订量较高"], product_url="https://example.com/1688/1-968970-1", image_url=_svg_data_url("#2f73d8")),
        _item(id="taobao-002", platform="淘宝", title="8-968970-1 相近型号蓝色汽车接插件", shop_name="线束端子配件仓", price=2.9, shipping_location="浙江 宁波", stock_status="现货 600 件", moq=20, key_parameters={"brand": "TE 同款", "part_number": "8-968970-1", "positions": "4P", "color": "蓝色", "type": "汽车插件"}, match_score=0.71, risk_tags=["相近型号风险", "不能直接替代需确认"], product_url="https://example.com/taobao/8-968970-1", image_url=_svg_data_url("#3777d4")),
        _item(id="other-001", platform="其他", title=f"TE Connectivity {part} 连接器采购代订", shop_name="Mouser 代购报价", price=12.4, shipping_location="海外仓", stock_status="预计 2-3 周", moq=1, key_parameters={"brand": "TE Connectivity", "part_number": part, "positions": "4P", "color": "蓝色", "type": "品牌渠道"}, match_score=0.94, risk_tags=["完全匹配", "交期不确定", "需核对含税运费"], product_url="https://example.com/distributor/1-968970-1", image_url=_svg_data_url("#2f73d8")),
        _item(id="1688-002", platform="1688", title="6-968970-1 相近规格连接器胶壳 批发", shop_name="温州端子连接器批发", price=0.18, price_type="abnormal", shipping_location="浙江 温州", stock_status="库存 20000 件", moq=1000, key_parameters={"brand": "未知", "part_number": "6-968970-1", "positions": "4P", "color": "蓝色", "type": "批发低价"}, match_score=0.63, risk_tags=["相近型号风险", "价格异常", "参数不完整"], product_url="https://example.com/1688/6-968970-1", image_url=_svg_data_url("#2f73d8")),
        _item(id="jd-002", platform="京东", title=f"{part} 蓝色连接器套装 含端子密封塞", shop_name="汽车线束配件旗舰店", price=9.9, shipping_location="上海", stock_status="现货 88 套", moq=1, key_parameters={"brand": "兼容套装", "part_number": part, "positions": "4P", "color": "蓝色", "type": "套装"}, match_score=0.88, risk_tags=["完全匹配", "套装价格不可直接对比单壳"], product_url="https://example.com/jd/kit-1-968970-1", image_url=_svg_data_url("#2f73d8")),
        _item(id="taobao-003", platform="淘宝", title="圆形防水连接器 4芯 黑色 航空插头", shop_name="工业圆形航空插头店", price=18.5, shipping_location="浙江 宁波", stock_status="现货 260 件", moq=2, key_parameters={"brand": "未知", "part_number": "非目标料号", "positions": "4芯", "color": "黑色", "type": "圆形防水连接器"}, match_score=0.42, risk_tags=["图片相似但型号不匹配", "非目标料号"], product_url="https://example.com/taobao/round-connector", image_url=_svg_data_url("#18191b", "round")),
    ]


def search_procurement(request: ProcurementSearchRequest) -> list[ProcurementResult]:
    provider_results = mock_procurement_results(request.query)
    allowed = set(request.platforms or ["淘宝", "京东", "1688", "其他"])
    filtered = [item for item in provider_results if item.platform in allowed]
    return sort_procurement_results(filtered, sort_by=request.sort_by, target_location=request.target_location)
