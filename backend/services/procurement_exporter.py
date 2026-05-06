from __future__ import annotations

import csv
import io

from services.procurement_models import ProcurementSearchRecord


CSV_COLUMNS = [
    "平台",
    "商品标题",
    "店铺",
    "价格",
    "价格类型",
    "发货地",
    "库存",
    "起订量",
    "匹配度",
    "风险标签",
    "品牌",
    "料号",
    "关键参数",
    "商品链接",
]


def procurement_search_to_csv(record: ProcurementSearchRecord) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for item in record.results:
        writer.writerow(
            {
                "平台": item.platform,
                "商品标题": item.title,
                "店铺": item.shop_name,
                "价格": item.price,
                "价格类型": item.price_type,
                "发货地": item.shipping_location,
                "库存": item.stock_status,
                "起订量": item.moq,
                "匹配度": item.match_score,
                "风险标签": "；".join(item.risk_tags),
                "品牌": item.key_parameters.get("brand", ""),
                "料号": item.key_parameters.get("part_number", ""),
                "关键参数": "；".join(f"{key}:{value}" for key, value in item.key_parameters.items()),
                "商品链接": item.product_url,
            }
        )
    return "\ufeff" + buffer.getvalue()
