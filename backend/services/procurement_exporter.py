from __future__ import annotations

import csv
import io

from services.procurement_models import ProcurementSearchRecord


CSV_COLUMNS = [
    "search_id",
    "query",
    "source_type",
    "source_name",
    "platform",
    "title",
    "shop_name",
    "search_summary_price",
    "currency",
    "price_type",
    "price_verification_status",
    "shipping_location",
    "shipping_verification_status",
    "stock_status",
    "stock_verification_status",
    "moq",
    "part_number",
    "match_score",
    "risk_tags",
    "product_url",
]


def procurement_search_to_csv(record: ProcurementSearchRecord) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for item in record.results:
        writer.writerow(
            {
                "search_id": record.search_id,
                "query": record.query,
                "source_type": item.source_type,
                "source_name": item.source_name,
                "platform": item.platform,
                "title": item.title,
                "shop_name": item.shop_name,
                "search_summary_price": "" if item.price is None else item.price,
                "currency": item.currency,
                "price_type": item.price_type,
                "price_verification_status": item.price_verification_status,
                "shipping_location": item.shipping_location,
                "shipping_verification_status": item.shipping_verification_status,
                "stock_status": item.stock_status,
                "stock_verification_status": item.stock_verification_status,
                "moq": item.moq,
                "part_number": item.key_parameters.get("part_number", ""),
                "match_score": item.match_score,
                "risk_tags": "；".join(item.risk_tags),
                "product_url": item.product_url,
            }
        )
    return "\ufeff" + buffer.getvalue()
