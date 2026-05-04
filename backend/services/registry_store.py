from __future__ import annotations

from pathlib import Path
from typing import Any

from services.json_store import atomic_write_json, file_lock, read_json

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = BACKEND_ROOT / "data"
REGISTRY_PATH = DATA_ROOT / "cad_registry.json"


def load_registry() -> dict[str, list[dict[str, Any]]]:
    return read_json(REGISTRY_PATH, {"items": []})


def save_registry(data: dict[str, Any]) -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {"items": data.get("items", [])}
    with file_lock(REGISTRY_PATH):
        atomic_write_json(REGISTRY_PATH, payload)
