from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from services.procurement_models import ProcurementResult
from services.procurement_source_config import normalize_platform_label


FIELD_ALIASES = {
    "title": ["商品标题", "标题", "title", "name", "商品名称"],
    "platform": ["平台", "platform"],
    "shop_name": ["店铺", "供应商", "shop_name", "supplier", "seller"],
    "price": ["价格", "price", "unit_price"],
    "currency": ["币种", "currency"],
    "shipping_location": ["发货地", "shipping_location", "location", "产地"],
    "stock_status": ["库存", "stock_status", "stock", "交期"],
    "moq": ["起订量", "moq", "MOQ", "最小起订量"],
    "product_url": ["商品链接", "product_url", "url", "link"],
    "image_url": ["图片链接", "image_url", "image", "thumbnail"],
    "brand": ["品牌", "brand"],
    "part_number": ["型号", "料号", "part_number", "mpn", "model"],
    "positions": ["孔位", "positions", "pin_count", "poles"],
    "color": ["颜色", "color"],
    "type": ["类型", "type", "category"],
    "notes": ["备注", "notes", "note"],
}


def _first(row: dict[str, Any], canonical: str) -> str:
    lower_row = {str(key).strip().lower(): value for key, value in row.items()}
    for alias in FIELD_ALIASES[canonical]:
        if alias in row and row[alias] not in (None, ""):
            return str(row[alias]).strip()
        value = lower_row.get(alias.lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def parse_price(value: str) -> float:
    match = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
    return float(match.group(0)) if match else 0.0


def parse_int(value: str, default: int = 1) -> int:
    match = re.search(r"\d+", value.replace(",", ""))
    return int(match.group(0)) if match else default


def normalize_part(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def build_offer_id(source_id: str, row_index: int, row: dict[str, Any]) -> str:
    digest = hashlib.sha1(repr(sorted(row.items())).encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"{source_id}-{row_index}-{digest}"


def score_imported_offer(query: str, title: str, part_number: str) -> tuple[float, list[str]]:
    normalized_query = normalize_part(query.split()[0] if query else "")
    normalized_part = normalize_part(part_number)
    normalized_title = normalize_part(title)
    if normalized_query and normalized_part == normalized_query:
        return 0.95, ["完全匹配", "报价表导入"]
    if normalized_query and normalized_query in normalized_title:
        return 0.88, ["标题匹配", "报价表导入"]
    if normalized_part and normalized_part in normalized_query or normalized_query in normalized_part:
        return 0.68, ["相近型号风险", "报价表导入"]
    return 0.45, ["需人工核对", "报价表导入"]


def normalize_offer_row(
    row: dict[str, Any],
    *,
    row_index: int,
    source_id: str,
    source_name: str,
    source_type: str,
    platform_label: str,
    import_id: str | None,
    query_hint: str = "",
) -> tuple[ProcurementResult | None, str | None]:
    title = _first(row, "title")
    price_text = _first(row, "price")
    if not title or not price_text:
        return None, f"第 {row_index} 行缺少商品标题或价格"

    platform = normalize_platform_label(_first(row, "platform") or platform_label)
    part_number = _first(row, "part_number")
    price = parse_price(price_text)
    if price <= 0:
        return None, f"第 {row_index} 行价格无效"

    price_type = "abnormal" if price < 0.2 else "normal"
    risk_tags = ["价格异常"] if price_type == "abnormal" else []
    match_score, match_tags = score_imported_offer(query_hint or part_number or title, title, part_number)
    for tag in match_tags:
        if tag not in risk_tags:
            risk_tags.append(tag)

    key_parameters = {
        "brand": _first(row, "brand") or "未标注",
        "part_number": part_number or "未标注",
        "positions": _first(row, "positions") or "未标注",
        "color": _first(row, "color") or "未标注",
        "type": _first(row, "type") or "连接器",
    }

    return (
        ProcurementResult(
            id=build_offer_id(source_id, row_index, row),
            title=title,
            platform=platform,  # type: ignore[arg-type]
            shop_name=_first(row, "shop_name") or source_name,
            price=price,
            currency=_first(row, "currency") or "CNY",
            price_type=price_type,  # type: ignore[arg-type]
            shipping_location=_first(row, "shipping_location") or "未标注",
            stock_status=_first(row, "stock_status") or "需询价",
            moq=parse_int(_first(row, "moq"), 1),
            image_url=_first(row, "image_url"),
            product_url=_first(row, "product_url") or "#",
            key_parameters=key_parameters,
            match_score=match_score,
            risk_tags=risk_tags,
            updated_at=datetime.now(timezone.utc).isoformat(),
            source_type=source_type,  # type: ignore[arg-type]
            source_name=source_name,
            import_id=import_id,
            data_freshness="manual_import" if source_type in {"csv_upload", "excel_upload"} else "live_api",
        ),
        None,
    )


def offer_matches_query(offer: ProcurementResult, query: str) -> bool:
    text = " ".join(
        [
            offer.title,
            offer.shop_name,
            str(offer.key_parameters.get("part_number", "")),
            str(offer.key_parameters),
        ]
    )
    normalized_query = normalize_part(query.split()[0] if query else "")
    normalized_text = normalize_part(text)
    return bool(normalized_query and normalized_query in normalized_text) or query.lower() in text.lower()
