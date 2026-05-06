from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Platform = Literal["淘宝", "京东", "1688", "其他"]
SortBy = Literal["price", "location", "match"]
PriceType = Literal["normal", "abnormal", "negotiable", "sample"]


class ProcurementSearchRequest(BaseModel):
    query: str
    target_location: str = ""
    platforms: list[Platform] = Field(default_factory=lambda: ["淘宝", "京东", "1688", "其他"])
    sort_by: SortBy = "price"
    image_search_enabled: bool = False


class ProcurementResult(BaseModel):
    id: str
    title: str
    platform: Platform
    shop_name: str
    price: float
    currency: str = "CNY"
    price_type: PriceType = "normal"
    shipping_location: str
    stock_status: str
    moq: int
    image_url: str
    product_url: str
    key_parameters: dict[str, Any]
    match_score: float
    risk_tags: list[str] = Field(default_factory=list)
    updated_at: str


class ProcurementSummary(BaseModel):
    total: int
    platform_counts: dict[str, int]
    lowest_price: float | None = None
    recommended_count: int


class ProcurementSearchRecord(BaseModel):
    search_id: str
    query: str
    target_location: str
    status: Literal["success", "failed"] = "success"
    results: list[ProcurementResult]
    summary: ProcurementSummary
    warnings: list[str]
    provider: str = "mock"
    sort_by: SortBy = "price"
    image_search_enabled: bool = False
