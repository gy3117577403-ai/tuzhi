from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from PIL import Image

from services.image_feature_extractor import extract_image_features


IMAGE_KEYWORD_ROOT = Path(__file__).resolve().parents[1] / "outputs" / "procurement_image_keywords"

COLOR_LABELS = {
    "blue": "蓝色",
    "black": "黑色",
    "grey": "灰色",
    "gray": "灰色",
    "white": "白色",
    "red": "红色",
}

SHAPE_LABELS = {
    "rectangular_housing": "矩形",
    "rounded_rectangular": "圆角矩形",
    "cylindrical_connector": "圆形",
}


def _position_label(features: dict[str, Any]) -> str:
    layout = features.get("front_face_layout") or {}
    active = int(layout.get("active_positions") or 0)
    candidates = features.get("cavity_candidates") or []
    if active <= 1 and len(candidates) > 1:
        active = len(candidates)
    if active <= 1:
        return ""
    return f"{active}P"


def _connector_type(features: dict[str, Any]) -> str:
    body_shape = features.get("body_shape")
    flags = features.get("feature_flags") or {}
    dominant = features.get("dominant_color")
    if body_shape == "cylindrical_connector":
        return "圆形连接器"
    if flags.get("wire_exit_rear") or flags.get("front_shroud") or dominant == "blue":
        return "汽车连接器"
    return "连接器"


def _confidence(features: dict[str, Any], positions: str) -> str:
    base = features.get("confidence") or "low"
    if positions and base == "medium":
        return "medium"
    if features.get("body_shape") and features.get("dominant_color"):
        return "medium"
    return "low"


def _keywords(detected: dict[str, str]) -> list[str]:
    color = detected.get("dominant_color", "")
    shape = detected.get("shape", "")
    positions = detected.get("positions_candidate", "")
    connector_type = detected.get("connector_type", "连接器")
    ocr_text = detected.get("ocr_text", "").strip()

    keywords: list[str] = []
    if ocr_text:
        keywords.append(f"{ocr_text} 连接器")
    if color and positions and connector_type:
        keywords.append(f"{color} {positions} {connector_type}")
    if positions:
        keywords.append(f"{positions.replace('P', '孔')}连接器")
    if color and shape and connector_type:
        keywords.append(f"{color}{shape}{connector_type}")
    if connector_type:
        keywords.append(connector_type)

    deduped: list[str] = []
    for keyword in keywords:
        text = " ".join(keyword.split())
        if text and text not in deduped:
            deduped.append(text)
    return deduped[:5] or ["连接器"]


async def extract_procurement_image_keywords(file: UploadFile) -> dict[str, Any]:
    filename = Path(file.filename or "connector_image.png").name
    suffix = Path(filename).suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        raise HTTPException(status_code=400, detail="仅支持常见图片格式")

    request_id = uuid.uuid4().hex
    output_dir = IMAGE_KEYWORD_ROOT / request_id
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / f"uploaded{suffix}"

    with image_path.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)

    try:
        with Image.open(image_path) as image:
            image.verify()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="上传文件不是可识别图片") from exc

    features = extract_image_features(image_path)
    color = COLOR_LABELS.get(str(features.get("dominant_color") or ""), "未知颜色")
    shape = SHAPE_LABELS.get(str(features.get("body_shape") or ""), "未知形状")
    positions = _position_label(features)
    connector_type = _connector_type(features)
    detected = {
        "dominant_color": color,
        "shape": shape,
        "positions_candidate": positions,
        "ocr_text": "",
        "connector_type": connector_type,
    }
    return {
        "status": "success",
        "keywords": _keywords(detected),
        "detected": detected,
        "confidence": _confidence(features, positions),
        "warnings": [
            "图片识别结果仅用于采购搜索关键词生成，需人工确认。",
            "当前未接入专用 OCR，图片文字识别可能为空。",
        ],
        "image_id": request_id,
    }
