from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.app.cad.generator import CADQUERY_AVAILABLE, CADQUERY_IMPORT_ERROR, DOWNLOAD_KINDS, build_params, generate_artifacts
from backend.app.models import InputMode, JobResponse

ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "generated"

app = FastAPI(title="Connector SmartCAD MVP", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "cadquery_available": CADQUERY_AVAILABLE,
        "cadquery_error": CADQUERY_IMPORT_ERROR or None,
    }


@app.post("/api/jobs", response_model=JobResponse)
async def create_job(
    mode: InputMode = Form(...),
    text: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
) -> JobResponse:
    if mode == InputMode.text and not (text or "").strip():
        raise HTTPException(status_code=400, detail="文本模式必须提供 text。")
    if mode != InputMode.text and file is None:
        raise HTTPException(status_code=400, detail="图纸/照片模式必须上传文件。")

    job_id = uuid.uuid4().hex
    output_dir = GENERATED_DIR / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    attachment_name = None
    if file is not None:
        attachment_name = Path(file.filename or "upload.bin").name
        attachment_path = output_dir / f"source_{attachment_name}"
        with attachment_path.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)

    params = build_params(mode=mode, text=text, attachment_name=attachment_name)
    try:
        generate_artifacts(params, output_dir)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CAD 生成失败: {exc}") from exc

    return _job_response(job_id, params)


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    params_path = _job_dir(job_id) / DOWNLOAD_KINDS["params"]
    if not params_path.exists():
        raise HTTPException(status_code=404, detail="任务不存在。")

    from backend.app.models import ConnectorParams

    params = ConnectorParams.model_validate_json(params_path.read_text(encoding="utf-8"))
    return _job_response(job_id, params)


@app.get("/api/jobs/{job_id}/download/{kind}")
def download(job_id: str, kind: str) -> FileResponse:
    if kind not in DOWNLOAD_KINDS:
        raise HTTPException(status_code=404, detail="不支持的导出类型。")
    path = _job_dir(job_id) / DOWNLOAD_KINDS[kind]
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在。")

    media_types = {
        "step": "application/step",
        "stp": "application/step",
        "dxf": "application/dxf",
        "stl": "model/stl",
        "glb": "model/gltf-binary",
        "params": "application/json",
    }
    return FileResponse(path, media_type=media_types[kind], filename=path.name)


def _job_response(job_id: str, params) -> JobResponse:
    return JobResponse(
        job_id=job_id,
        status="completed",
        params=params,
        preview_url=f"/api/jobs/{job_id}/download/stl",
        downloads={kind: f"/api/jobs/{job_id}/download/{kind}" for kind in DOWNLOAD_KINDS},
    )


def _job_dir(job_id: str) -> Path:
    if not job_id or any(char not in "0123456789abcdef" for char in job_id) or len(job_id) != 32:
        raise HTTPException(status_code=400, detail="非法任务 ID。")
    return GENERATED_DIR / job_id
