from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image, UnidentifiedImageError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MAX_IMAGE_BYTES = 15 * 1024 * 1024
ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def download_image_to_job(image_url: str, output_dir: Path, filename_prefix: str = "selected_image") -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    url = (image_url or "").strip()
    try:
        if url.startswith("/api/test-assets/"):
            return _copy_test_asset(url, output_dir, filename_prefix)
        if url.startswith("file://"):
            return _copy_file_url(url, output_dir, filename_prefix)
        if not url.startswith(("http://", "https://")):
            raise ValueError("image_url must be http(s), file://, or /api/test-assets/... for mock tests")

        with httpx.Client(timeout=45.0, follow_redirects=True, headers={"User-Agent": "ConnectorCAD-MVP/1.0"}) as client:
            response = client.get(url)
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").split(";")[0].lower()
            if content_type not in ALLOWED_TYPES:
                raise ValueError(f"Unsupported image content-type: {content_type or 'unknown'}")
            data = response.content
            if len(data) > MAX_IMAGE_BYTES:
                raise ValueError("Image exceeds 15MB limit")
            suffix = ALLOWED_TYPES[content_type]
            path = output_dir / f"{filename_prefix}{suffix}"
            path.write_bytes(data)
            return _payload(path, content_type, warnings)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "saved_path": "",
            "filename": "",
            "content_type": "",
            "size_bytes": 0,
            "sha256": "",
            "image_width": 0,
            "image_height": 0,
            "decode_ok": False,
            "download_warnings": warnings,
            "warnings": warnings,
        }


def _copy_test_asset(url: str, output_dir: Path, filename_prefix: str) -> dict[str, Any]:
    name = Path(urlparse(url).path).name
    source = BACKEND_ROOT / "test_assets" / name
    if not source.exists():
        raise FileNotFoundError(f"Mock test asset not found: {name}")
    suffix = source.suffix.lower()
    content_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(suffix)
    if content_type not in ALLOWED_TYPES:
        raise ValueError("Unsupported local test image type")
    target = output_dir / f"{filename_prefix}{suffix}"
    shutil.copyfile(source, target)
    return _payload(target, content_type, [])


def _copy_file_url(url: str, output_dir: Path, filename_prefix: str) -> dict[str, Any]:
    raw_path = urlparse(url).path.lstrip("/")
    source = Path(raw_path)
    if not source.is_absolute():
        source = BACKEND_ROOT / source.relative_to("backend") if raw_path.startswith("backend/") else Path.cwd() / source
    if not source.exists():
        raise FileNotFoundError(f"Image file not found: {source}")
    suffix = source.suffix.lower()
    content_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(suffix)
    if content_type not in ALLOWED_TYPES:
        raise ValueError("Unsupported image file type")
    if source.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds 15MB limit")
    target = output_dir / f"{filename_prefix}{suffix}"
    shutil.copyfile(source, target)
    return _payload(target, content_type, [])


def _payload(path: Path, content_type: str, warnings: list[str]) -> dict[str, Any]:
    decode = _decode_image(path)
    if not decode["decode_ok"]:
        raise ValueError(decode["error"] or "Downloaded file is not a decodable image")
    return {
        "ok": True,
        "saved_path": str(path),
        "filename": path.name,
        "content_type": content_type,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "image_width": decode["image_width"],
        "image_height": decode["image_height"],
        "decode_ok": True,
        "download_warnings": warnings,
        "warnings": warnings,
    }


def _decode_image(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            header = handle.read(16)
        if header.lstrip().lower().startswith((b"<!doctype", b"<html", b"{", b"[")):
            return {"decode_ok": False, "image_width": 0, "image_height": 0, "error": "Downloaded content is not an image"}
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            w, h = img.size
        return {"decode_ok": True, "image_width": int(w), "image_height": int(h), "error": ""}
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        return {"decode_ok": False, "image_width": 0, "image_height": 0, "error": str(exc)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
