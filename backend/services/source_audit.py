from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from services.domain_policy import classify_source_url

PRODUCTION_USE_WARNING = "Verify CAD source, revision, and manufacturer terms before using for production."


def create_source_manifest(job_id, output_dir, source_result, generated_files, model_origin, status):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    source_url = source_result.get("source_url", "")
    cad_url = source_result.get("cad_url", "")
    source_domain = classify_source_url(source_url or cad_url)

    original = output_path / "official_original.step"
    download = {
        "official_cad_downloaded": bool(source_result.get("official_cad_downloaded", False)),
        "original_filename": _original_filename(cad_url),
        "saved_as": "official_original.step" if original.exists() else "",
        "downloaded_at": _now(),
        "file_size_bytes": original.stat().st_size if original.exists() else 0,
        "sha256": _sha256(original) if original.exists() else "",
    }

    generated = {}
    for key, filename in {
        "step": "model.step",
        "stl": "model.stl",
        "dxf": "drawing.dxf",
        "params": "params.json",
    }.items():
        file_path = output_path / filename
        if file_path.exists():
            generated[key] = {
                "path": filename,
                "size_bytes": file_path.stat().st_size,
                "sha256": _sha256(file_path),
            }

    manifest = {
        "job_id": job_id,
        "created_at": _now(),
        "model_origin": model_origin,
        "status": status,
        "source_type": source_result.get("source_type", "not_found"),
        "source_url": source_url,
        "cad_url": cad_url,
        "source_domain": source_domain,
        "download": download,
        "generated_files": generated,
        "license_note": source_result.get("license_note", "User should verify manufacturer CAD terms before production use."),
        "registry_item_id": source_result.get("registry_item_id"),
        "registry_candidate_id": source_result.get("registry_candidate_id"),
        "registry_status": source_result.get("registry_status"),
        "revision": source_result.get("revision"),
        "version_label": source_result.get("version_label"),
        "registry_sha256": source_result.get("registry_sha256"),
        "selection_reason": source_result.get("selection_reason"),
        "available_versions": source_result.get("available_versions", []),
        "registry_cache_status": source_result.get("registry_cache_status"),
        "cached_file_used": bool(source_result.get("cached_file_used", False)),
        "cached_file_sha256": source_result.get("cached_file_sha256"),
        "cache_metadata_path": source_result.get("cache_metadata_path"),
        "preferred_revision": source_result.get("preferred_revision"),
        "preferred_version_label": source_result.get("preferred_version_label"),
        "registry": {
            "registry_item_id": source_result.get("registry_item_id"),
            "registry_candidate_id": source_result.get("registry_candidate_id"),
            "revision": source_result.get("revision"),
            "version_label": source_result.get("version_label"),
            "selection_reason": source_result.get("selection_reason"),
            "cached_file_used": bool(source_result.get("cached_file_used", False)),
            "cache_metadata_path": source_result.get("cache_metadata_path"),
            "available_versions": source_result.get("available_versions", []),
        },
        "production_use_warning": PRODUCTION_USE_WARNING,
    }
    manifest_path = output_path / "source_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def summarize_manifest(manifest: dict) -> dict:
    generated_files = manifest.get("generated_files", {})
    return {
        "model_origin": manifest.get("model_origin"),
        "source_type": manifest.get("source_type"),
        "source_category": manifest.get("source_domain", {}).get("category", "unknown"),
        "is_approved_source": bool(manifest.get("source_domain", {}).get("is_approved", False)),
        "has_sha256": any(bool(item.get("sha256")) for item in generated_files.values()),
        "production_use_warning": manifest.get("production_use_warning", PRODUCTION_USE_WARNING),
        "downloaded_at": manifest.get("download", {}).get("downloaded_at", ""),
        "registry_item_id": manifest.get("registry_item_id"),
        "registry_candidate_id": manifest.get("registry_candidate_id"),
        "revision": manifest.get("revision"),
        "version_label": manifest.get("version_label"),
        "registry_sha256": manifest.get("registry_sha256"),
        "selection_reason": manifest.get("selection_reason"),
        "cached_file_used": manifest.get("cached_file_used", False),
    }


def augment_params_json(output_dir: Path, manifest: dict) -> None:
    params_path = output_dir / "params.json"
    if not params_path.exists():
        return
    payload = json.loads(params_path.read_text(encoding="utf-8"))
    generated = manifest.get("generated_files", {})
    payload["source_manifest"] = "source_manifest.json"
    payload["source_domain_category"] = manifest.get("source_domain", {}).get("category", "unknown")
    payload["source_domain_approved"] = bool(manifest.get("source_domain", {}).get("is_approved", False))
    payload["file_hashes"] = {
        item["path"]: item["sha256"]
        for item in generated.values()
        if item.get("path") != "params.json" and item.get("sha256")
    }
    for key in [
        "registry_item_id",
        "registry_candidate_id",
        "registry_status",
        "revision",
        "version_label",
        "registry_sha256",
        "registry_cache_status",
        "cached_file_used",
        "cached_file_sha256",
        "cache_metadata_path",
        "selection_reason",
        "available_versions",
        "preferred_revision",
        "preferred_version_label",
    ]:
        if manifest.get(key) is not None:
            payload[key] = manifest.get(key)
    params_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _original_filename(cad_url: str) -> str:
    if not cad_url:
        return ""
    parsed = urlparse(cad_url)
    return Path(parsed.path).name or "official_original.step"
