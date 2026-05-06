from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import HTTPException

from services.procurement_models import ProcurementSourceConfig, ProcurementSourceCreateRequest, ProcurementSourceUpdateRequest
from services.procurement_source_config import DATA_SOURCE_NOTICE, now_iso, public_source_config


PROCUREMENT_DATA_DIR = Path(__file__).resolve().parents[1] / "outputs" / "procurement_data"
SOURCES_FILE = PROCUREMENT_DATA_DIR / "sources.json"


def _ensure_dir() -> None:
    PROCUREMENT_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _default_sources() -> list[dict]:
    timestamp = now_iso()
    return [
        {
            "source_id": "mock",
            "source_name": "内置 mock 商品数据",
            "source_type": "mock",
            "enabled": True,
            "priority": 100,
            "platform_label": "其他",
            "notes": DATA_SOURCE_NOTICE,
            "created_at": timestamp,
            "updated_at": timestamp,
            "auth_mode": "none",
            "safe_mode": True,
        }
    ]


def load_sources() -> list[ProcurementSourceConfig]:
    _ensure_dir()
    if not SOURCES_FILE.exists():
        SOURCES_FILE.write_text(json.dumps(_default_sources(), ensure_ascii=False, indent=2), encoding="utf-8")
    raw = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    return [ProcurementSourceConfig(**public_source_config(item)) for item in raw]


def save_sources(sources: list[ProcurementSourceConfig]) -> None:
    _ensure_dir()
    SOURCES_FILE.write_text(
        json.dumps([source.model_dump() for source in sources], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_sources() -> list[dict]:
    return [source.model_dump() for source in load_sources()]


def create_source(payload: ProcurementSourceCreateRequest) -> ProcurementSourceConfig:
    sources = load_sources()
    timestamp = now_iso()
    source = ProcurementSourceConfig(
        source_id=uuid.uuid4().hex,
        source_name=payload.source_name.strip() or "未命名采购数据源",
        source_type=payload.source_type,
        enabled=payload.enabled,
        priority=payload.priority,
        platform_label=payload.platform_label,
        notes=payload.notes,
        created_at=timestamp,
        updated_at=timestamp,
        auth_mode=payload.auth_mode,
        safe_mode=payload.safe_mode,
    )
    sources.append(source)
    save_sources(sources)
    return source


def update_source(source_id: str, payload: ProcurementSourceUpdateRequest) -> ProcurementSourceConfig:
    sources = load_sources()
    for index, source in enumerate(sources):
        if source.source_id == source_id:
            data = source.model_dump()
            for key, value in payload.model_dump(exclude_unset=True).items():
                if value is not None:
                    data[key] = value
            data["updated_at"] = now_iso()
            updated = ProcurementSourceConfig(**data)
            sources[index] = updated
            save_sources(sources)
            return updated
    raise HTTPException(status_code=404, detail="procurement source not found")


def delete_source(source_id: str) -> dict:
    if source_id == "mock":
        raise HTTPException(status_code=400, detail="mock source cannot be deleted")
    sources = load_sources()
    kept = [source for source in sources if source.source_id != source_id]
    if len(kept) == len(sources):
        raise HTTPException(status_code=404, detail="procurement source not found")
    save_sources(kept)
    return {"deleted": True, "source_id": source_id}
