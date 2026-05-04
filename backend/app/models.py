from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class InputMode(str, Enum):
    text = "text"
    drawing = "drawing"
    photo = "photo"


class UnknownDimension(BaseModel):
    name: str
    label: str
    status: Literal["待确认"] = "待确认"
    reason: str


class ConnectorDimensions(BaseModel):
    overall_length: float = Field(..., description="mm")
    overall_width: float = Field(..., description="mm")
    overall_height: float = Field(..., description="mm")
    cavity_length: float = Field(..., description="mm")
    cavity_width: float = Field(..., description="mm")
    cavity_depth: float = Field(..., description="mm")
    pin_count: int
    pin_rows: int
    pin_pitch: float = Field(..., description="mm")
    pin_diameter: float = Field(..., description="mm")
    mount_hole_diameter: float = Field(..., description="mm")
    mount_hole_spacing: float = Field(..., description="mm")
    lock_width: float = Field(..., description="mm")
    lock_depth: float = Field(..., description="mm")
    lock_height: float = Field(..., description="mm")
    fillet_radius: float = Field(..., description="mm")
    chamfer: float = Field(..., description="mm")


class ConnectorParams(BaseModel):
    title: str
    description: str
    unit: Literal["mm"] = "mm"
    source: Literal["mvp_default", "text_heuristic", "uploaded_file_unverified"]
    input_mode: InputMode
    input_text: str | None = None
    attachment_name: str | None = None
    dimensions: ConnectorDimensions
    unknowns: list[UnknownDimension]


class JobResponse(BaseModel):
    job_id: str
    status: Literal["completed", "failed"]
    params: ConnectorParams | None = None
    preview_url: str | None = None
    downloads: dict[str, str] = {}
    error: str | None = None
