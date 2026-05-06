from __future__ import annotations

from services.procurement_models import ProcurementResult


NEAR_REGIONS = {
    "浙江": {"上海", "江苏", "安徽"},
    "广东": {"福建", "广西", "湖南"},
    "江苏": {"上海", "浙江", "安徽"},
    "上海": {"江苏", "浙江"},
}


def location_score(shipping_location: str, target_location: str) -> int:
    shipping = (shipping_location or "").replace(" ", "")
    target = (target_location or "").replace(" ", "")
    if not target:
        return 0
    if shipping and (shipping in target or target in shipping):
        return 40
    target_parts = [part for part in (target_location or "").split() if part]
    score = 0
    for part in target_parts:
        if part and part in shipping:
            score += 15
    target_province = target_parts[0] if target_parts else ""
    shipping_province = (shipping_location or "").split()[0] if shipping_location else ""
    if target_province and shipping_province and target_province == shipping_province:
        score += 20
    if target_province in NEAR_REGIONS and shipping_province in NEAR_REGIONS[target_province]:
        score += 8
    return score


def is_abnormal_price(result: ProcurementResult) -> bool:
    return result.price_type == "abnormal" or any("价格异常" in tag for tag in result.risk_tags)


def price_sort_bucket(result: ProcurementResult) -> tuple[int, float]:
    if result.price_type == "normal" and result.price is not None and result.price > 0:
        return (0, float(result.price))
    if result.price_type in {"unknown", "negotiable", "sample"} or result.price is None:
        return (1, 1e12)
    if is_abnormal_price(result):
        return (2, float(result.price or 1e12))
    return (1, float(result.price or 1e12))


def sort_procurement_results(
    results: list[ProcurementResult],
    *,
    sort_by: str,
    target_location: str,
) -> list[ProcurementResult]:
    if sort_by == "location":
        return sorted(
            results,
            key=lambda item: (
                -location_score(item.shipping_location, target_location),
                price_sort_bucket(item),
                -item.match_score,
            ),
        )
    if sort_by == "match":
        return sorted(results, key=lambda item: (-item.match_score, price_sort_bucket(item)))
    return sorted(results, key=lambda item: (price_sort_bucket(item), -item.match_score))
