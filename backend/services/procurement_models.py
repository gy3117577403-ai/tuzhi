from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Platform = Literal["淘宝", "京东", "1688", "其他"]
SortBy = Literal["price", "location", "match"]
PriceType = Literal["normal", "abnormal", "negotiable", "sample"]
SourceType = Literal["mock", "csv_upload", "excel_upload", "generic_json", "supplier_api"]
AuthMode = Literal["none", "api_key", "bearer", "custom"]


class ProcurementSearchRequest(BaseModel):
    query: str
    target_location: str = ""
    platforms: list[Platform] = Field(default_factory=lambda: ["淘宝", "京东", "1688", "其他"])
    sort_by: SortBy = "price"
    image_search_enabled: bool = False
    source_types: list[SourceType] | None = None


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
    source_type: SourceType = "mock"
    source_name: str = "内置 mock 数据"
    import_id: str | None = None
    data_freshness: Literal["manual_import", "live_api", "mock"] = "mock"


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


class ProcurementSourceConfig(BaseModel):
    source_id: str
    source_name: str
    source_type: SourceType
    enabled: bool = True
    priority: int = 1
    platform_label: Platform | str = "其他"
    notes: str = ""
    created_at: str
    updated_at: str
    auth_mode: AuthMode = "none"
    safe_mode: bool = True


class ProcurementImportResponse(BaseModel):
    import_id: str
    source_name: str
    source_type: SourceType
    rows_total: int
    rows_imported: int
    rows_skipped: int
    warnings: list[str] = Field(default_factory=list)
    offers: list[ProcurementResult] = Field(default_factory=list)


class ProcurementSourceCreateRequest(BaseModel):
    source_name: str
    source_type: SourceType = "generic_json"
    enabled: bool = True
    priority: int = 1
    platform_label: Platform | str = "其他"
    notes: str = ""
    auth_mode: AuthMode = "none"
    safe_mode: bool = True


class ProcurementSourceUpdateRequest(BaseModel):
    source_name: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    platform_label: Platform | str | None = None
    notes: str | None = None
    auth_mode: AuthMode | None = None
    safe_mode: bool | None = None
