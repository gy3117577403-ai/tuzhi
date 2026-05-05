from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from services.connector_params import ConnectorCadParams

BACKEND_ROOT = Path(__file__).resolve().parents[1]
OUTPUTS_ROOT = BACKEND_ROOT / "outputs"


def new_job_id() -> str:
    return uuid.uuid4().hex


def job_dir(job_id: str) -> Path:
    if len(job_id) != 32 or any(char not in "0123456789abcdef" for char in job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    return OUTPUTS_ROOT / job_id


def create_job_dir(job_id: str) -> Path:
    directory = job_dir(job_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_upload(job_id: str, upload: UploadFile | None) -> str | None:
    if upload is None:
        return None
    safe_name = Path(upload.filename or "upload.bin").name
    target = create_job_dir(job_id) / f"source_{safe_name}"
    with target.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)
    return safe_name


def load_params(job_id: str) -> ConnectorCadParams:
    path = job_dir(job_id) / "job_state.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return ConnectorCadParams.model_validate_json(path.read_text(encoding="utf-8"))


def save_params(job_id: str, params: ConnectorCadParams) -> None:
    path = create_job_dir(job_id) / "job_state.json"
    path.write_text(json.dumps(params.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


JOB_ARTIFACT_FILENAMES = frozenset(
    {
        "model.step",
        "model.stl",
        "drawing.dxf",
        "params.json",
        "source_manifest.json",
        "image_features.json",
        "vision_report.json",
        "image_search_results.json",
        "selected_image.json",
        "visual_recipe.json",
        "connector_front_view.dxf",
        "connector_rear_view.dxf",
        "connector_top_view.dxf",
        "connector_side_view.dxf",
        "connector_insertion_direction.dxf",
        "connector_flat_views.svg",
        "connector_2d_recipe.json",
        "connector_view_classification.json",
        "terminal_insertion.json",
        "structure_completeness_report.json",
        "sop_wi_draft.json",
        "sop_wi_draft.html",
        "sop_wi_summary.md",
        "engineering_confirmation_checklist.json",
        "sop_wi_assets_manifest.json",
        "sop_wi_draft.pdf",
        "confirmation_status.json",
        "sop_wi_signed.html",
        "sop_wi_signed.json",
        "sop_wi_signed_summary.md",
        "sop_wi_signed.pdf",
    }
)


def file_path(job_id: str, filename: str) -> Path:
    allowed = JOB_ARTIFACT_FILENAMES
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="Unsupported file")
    path = job_dir(job_id) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return path
