from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

InputType = Literal["text", "drawing", "photo"]
JobStatus = Literal["generating", "needs_confirmation", "completed", "failed"]
DimensionSource = Literal["default_mvp", "text_hint", "user_confirmed", "ai_extracted", "registry_template"]
Confidence = Literal["low", "medium", "high", "manual_pending"]
ModelOrigin = Literal[
    "official_cad",
    "third_party_cad",
    "parametric_mvp",
    "series_template",
    "image_approximated",
    "image_search_approximated",
    "image_upload_approximated",
    "generic_mvp",
]
SourceType = Literal["official_cad", "official_candidate", "third_party", "not_found", "local_test"]

PARAMETRIC_DISCLAIMER = "This is a parametric engineering approximation, not an official manufacturer CAD model."
OFFICIAL_LICENSE_NOTE = "User should verify manufacturer CAD terms before production use."
PROVISIONAL_WARNING = "当前 CAD 为参数化近似预览版，关键尺寸未确认。"


class DimensionValue(BaseModel):
    value: float | int
    unit: str = "mm"
    source: DimensionSource = "default_mvp"
    confidence: Confidence = "medium"


class ConnectorCadParams(BaseModel):
    title: str
    part_number: str
    model_type: Literal["parametric_mvp_connector"] = "parametric_mvp_connector"
    disclaimer: str = PARAMETRIC_DISCLAIMER
    input_type: InputType
    status: JobStatus = "generating"
    is_provisional: bool = True
    warning: str | None = PROVISIONAL_WARNING
    source: DimensionSource = "default_mvp"
    dimensions: dict[str, DimensionValue]
    unknown_fields: list[str]
    accepted_unknowns: list[str] = Field(default_factory=list)
    notes: str | None = None
    error: str | None = None
    model_origin: ModelOrigin = "generic_mvp"
    source_type: SourceType = "not_found"
    manufacturer: str | None = None
    official_candidate_found: bool = False
    official_cad_downloaded: bool = False
    fallback_reason: str | None = None
    source_url: str = ""
    cad_url: str = ""
    license_note: str = OFFICIAL_LICENSE_NOTE
    source_manifest: str | None = None
    source_domain_category: str | None = None
    source_domain_approved: bool | None = None
    file_hashes: dict[str, str] = Field(default_factory=dict)
    registry_item_id: str | None = None
    registry_candidate_id: str | None = None
    registry_status: str | None = None
    revision: str | None = None
    version_label: str | None = None
    registry_sha256: str | None = None
    registry_cache_status: str | None = None
    cached_file_used: bool = False
    cached_file_sha256: str | None = None
    cache_metadata_path: str | None = None
    cached_at: str | None = None
    selection_reason: str | None = None
    available_versions: list[dict[str, Any]] = Field(default_factory=list)
    preferred_revision: str | None = None
    preferred_version_label: str | None = None
    generation_files: dict[str, str] = Field(
        default_factory=lambda: {"step": "model.step", "stl": "model.stl", "dxf": "drawing.dxf"}
    )
    ai_extraction: dict[str, Any] | None = None
    template_name: str | None = None
    appearance_confidence: str | None = None
    visual_match: dict[str, Any] | None = None
    preview_style: dict[str, Any] | None = None
    appearance_pipeline: dict[str, Any] | None = None
    image_feature_summary: dict[str, Any] | None = None
    vision_report_summary: dict[str, Any] | None = None
    image_fallback_warning: str | None = None
    visual_recipe: dict[str, Any] | None = None
    geometry_basis: str | None = None
    manufacturing_accuracy: str | None = None
    image_search_context: dict[str, Any] | None = None
    image_search: dict[str, Any] | None = None
    uploaded_file_name: str | None = None
    flat_cad: dict[str, Any] | None = None
    sop_wi: dict[str, Any] | None = None


DEFAULT_DIMENSIONS: dict[str, DimensionValue] = {
    "overall_length": DimensionValue(value=36.0),
    "overall_width": DimensionValue(value=18.0),
    "overall_height": DimensionValue(value=14.0),
    "cavity_length": DimensionValue(value=22.0),
    "cavity_width": DimensionValue(value=9.0),
    "cavity_depth": DimensionValue(value=4.0),
    "pin_count": DimensionValue(value=2, unit="count"),
    "pin_rows": DimensionValue(value=1, unit="count"),
    "pin_pitch": DimensionValue(value=6.0),
    "pin_diameter": DimensionValue(value=2.0),
    "mount_hole_diameter": DimensionValue(value=3.0),
    "mount_hole_spacing": DimensionValue(value=28.0),
    "lock_width": DimensionValue(value=14.0),
    "lock_depth": DimensionValue(value=2.0),
    "lock_height": DimensionValue(value=2.2),
    "edge_radius": DimensionValue(value=0.8),
    "chamfer": DimensionValue(value=0.35),
}

UNKNOWN_FIELDS = ["exact_latch_geometry", "exact_shell_profile"]

CAD_TO_INTERNAL = {
    "positions": ("pin_count", "count"),
    "pitch_mm": ("pin_pitch", "mm"),
    "body_length_mm": ("overall_length", "mm"),
    "body_width_mm": ("overall_width", "mm"),
    "body_height_mm": ("overall_height", "mm"),
    "cavity_diameter_mm": ("pin_diameter", "mm"),
    "mounting_hole_spacing_mm": ("mount_hole_spacing", "mm"),
    "mounting_hole_diameter_mm": ("mount_hole_diameter", "mm"),
}


def build_initial_params(input_type: InputType, text: str | None, filename: str | None) -> ConnectorCadParams:
    dimensions = {key: value.model_copy(deep=True) for key, value in DEFAULT_DIMENSIONS.items()}
    normalized = (text or "").strip()

    pin_count = _extract_pin_count(normalized)
    pitch = _extract_pitch(normalized)
    if pin_count:
        dimensions["pin_count"] = DimensionValue(value=pin_count, unit="count", source="text_hint", confidence="medium")
        rows = 2 if pin_count > 8 else 1
        dimensions["pin_rows"] = DimensionValue(value=rows, unit="count", source="text_hint", confidence="medium")
    if pitch:
        dimensions["pin_pitch"] = DimensionValue(value=pitch, source="text_hint", confidence="medium")
    if pin_count or pitch:
        _derive_body_from_pin_array(dimensions)

    source: DimensionSource = "text_hint" if input_type == "text" and (pin_count or pitch) else "default_mvp"
    title = normalized[:80] if normalized else "Generic rectangular connector MVP"
    if filename:
        title = f"Generic connector from {filename}"

    return ConnectorCadParams(
        title=title,
        part_number=title,
        input_type=input_type,
        source=source,
        status="needs_confirmation",
        is_provisional=True,
        warning=PROVISIONAL_WARNING,
        dimensions=dimensions,
        unknown_fields=UNKNOWN_FIELDS.copy(),
    )


def build_official_params(input_type: InputType, text: str | None, cad_source: dict[str, Any]) -> ConnectorCadParams:
    title = cad_source.get("part_number") or (text or "Official CAD")
    source_type = cad_source.get("source_type", "official_cad")
    model_origin: ModelOrigin = "third_party_cad" if source_type == "third_party" else "official_cad"
    return ConnectorCadParams(
        title=title,
        part_number=cad_source.get("part_number") or title,
        disclaimer="Official or user-provided CAD file was used as the model source. Verify CAD terms before production use.",
        input_type=input_type,
        status="completed",
        is_provisional=False,
        warning=None,
        source="user_confirmed",
        dimensions={},
        unknown_fields=[],
        model_origin=model_origin,
        source_type=source_type,
        manufacturer=cad_source.get("manufacturer"),
        official_candidate_found=True,
        official_cad_downloaded=True,
        source_url=cad_source.get("source_url", ""),
        cad_url=cad_source.get("cad_url", ""),
        license_note=cad_source.get("license_note", OFFICIAL_LICENSE_NOTE),
        registry_item_id=cad_source.get("registry_item_id"),
        registry_status=cad_source.get("registry_status"),
        revision=cad_source.get("revision"),
        version_label=cad_source.get("version_label"),
        registry_sha256=cad_source.get("registry_sha256"),
        registry_cache_status=cad_source.get("registry_cache_status"),
        cached_file_used=bool(cad_source.get("cached_file_used", False)),
        cached_file_sha256=cad_source.get("cached_file_sha256"),
        cache_metadata_path=cad_source.get("cache_metadata_path"),
        cached_at=cad_source.get("cached_at"),
        selection_reason=cad_source.get("selection_reason"),
        available_versions=cad_source.get("available_versions", []),
        preferred_revision=cad_source.get("preferred_revision"),
        preferred_version_label=cad_source.get("preferred_version_label"),
    )


def apply_cad_source_metadata(params: ConnectorCadParams, cad_source: dict[str, Any]) -> ConnectorCadParams:
    next_params = params.model_copy(deep=True)
    source_type = cad_source.get("source_type", "not_found")
    next_params.source_type = source_type
    next_params.manufacturer = cad_source.get("manufacturer")
    next_params.official_candidate_found = source_type in {"official_cad", "official_candidate"}
    next_params.official_cad_downloaded = False
    next_params.source_url = cad_source.get("source_url", "")
    next_params.cad_url = cad_source.get("cad_url", "")
    next_params.license_note = cad_source.get("license_note", OFFICIAL_LICENSE_NOTE)
    next_params.registry_candidate_id = cad_source.get("registry_candidate_id")
    next_params.registry_item_id = cad_source.get("registry_item_id")
    next_params.registry_status = cad_source.get("registry_status")
    next_params.revision = cad_source.get("revision")
    next_params.version_label = cad_source.get("version_label")
    next_params.registry_sha256 = cad_source.get("registry_sha256")
    next_params.registry_cache_status = cad_source.get("registry_cache_status")
    next_params.cached_file_used = bool(cad_source.get("cached_file_used", False))
    next_params.cached_file_sha256 = cad_source.get("cached_file_sha256")
    next_params.cache_metadata_path = cad_source.get("cache_metadata_path")
    next_params.cached_at = cad_source.get("cached_at")
    next_params.selection_reason = cad_source.get("selection_reason")
    next_params.available_versions = cad_source.get("available_versions", [])
    next_params.preferred_revision = cad_source.get("preferred_revision")
    next_params.preferred_version_label = cad_source.get("preferred_version_label")
    next_params.model_origin = "third_party_cad" if source_type == "third_party" else "generic_mvp"
    if source_type == "official_candidate":
        next_params.fallback_reason = cad_source.get("fallback_reason") or "official CAD URL not configured"
    elif source_type == "not_found":
        next_params.fallback_reason = "official CAD source not found"
    elif source_type == "third_party":
        next_params.fallback_reason = "third-party CAD requires verification; using parametric MVP fallback"
    return next_params


def apply_visual_registry_item(params: ConnectorCadParams, item: dict[str, Any]) -> ConnectorCadParams:
    """Apply registry template dimensions and metadata for series-template CAD."""
    next_params = params.model_copy(deep=True)
    tp = item.get("template_params") or {}
    if "body_length_mm" in tp:
        next_params.dimensions["overall_length"] = DimensionValue(
            value=float(tp["body_length_mm"]), source="registry_template", confidence="high"
        )
    if "body_width_mm" in tp:
        next_params.dimensions["overall_width"] = DimensionValue(
            value=float(tp["body_width_mm"]), source="registry_template", confidence="high"
        )
    if "body_height_mm" in tp:
        next_params.dimensions["overall_height"] = DimensionValue(
            value=float(tp["body_height_mm"]), source="registry_template", confidence="high"
        )
    if "cavity_diameter_mm" in tp:
        cd = float(tp["cavity_diameter_mm"])
        next_params.dimensions["pin_diameter"] = DimensionValue(
            value=round(cd / 1.6, 4),
            source="registry_template",
            confidence="high",
        )
    if item.get("positions") is not None:
        pc = max(1, int(item["positions"]))
        next_params.dimensions["pin_count"] = DimensionValue(value=pc, unit="count", source="registry_template", confidence="high")
        rows = 2 if pc > 8 else 1
        next_params.dimensions["pin_rows"] = DimensionValue(value=rows, unit="count", source="registry_template", confidence="high")
    _derive_body_from_pin_array(next_params.dimensions, overwrite_defaults=False)
    if item.get("manufacturer"):
        next_params.manufacturer = str(item["manufacturer"])
    if item.get("part_number"):
        next_params.part_number = str(item["part_number"])
        next_params.title = item.get("display_name") or str(item["part_number"])
    next_params.visual_match = {
        "matched_from_registry": True,
        "registry_item_id": item.get("id"),
        "selection_reason": "Matched part_visual_registry entry.",
        "front_face_layout": item.get("front_face_layout"),
    }
    next_params.preview_style = {"base_color": item.get("color") or "grey"}
    return next_params


CAD_EXTRACT_KEY_TO_INTERNAL: dict[str, str] = {
    "positions": "pin_count",
    "pitch_mm": "pin_pitch",
    "body_length_mm": "overall_length",
    "body_width_mm": "overall_width",
    "body_height_mm": "overall_height",
    "cavity_diameter_mm": "pin_diameter",
    "mounting_hole_spacing_mm": "mount_hole_spacing",
    "mounting_hole_diameter_mm": "mount_hole_diameter",
}


def merge_ai_extracted_into_params(
    params: ConnectorCadParams,
    extracted: dict[str, Any],
    ai_extraction: dict[str, Any],
) -> ConnectorCadParams:
    """Merge AI JSON extraction into parametric dimensions; records ai_extraction block."""
    next_params = params.model_copy(deep=True)
    next_params.ai_extraction = ai_extraction

    raw_conf = str(extracted.get("confidence") or "low").lower().strip()
    ai_conf: Confidence = raw_conf if raw_conf in {"low", "medium", "high"} else "low"  # type: ignore[assignment]

    mfg = str(extracted.get("manufacturer") or "").strip()
    pn = str(extracted.get("part_number") or "").strip()
    ctype = str(extracted.get("connector_type") or "").strip()
    if mfg:
        next_params.manufacturer = mfg
    if pn:
        next_params.part_number = pn
    if mfg and pn:
        next_params.title = f"{mfg} {pn}".strip()

    notes = str(extracted.get("notes") or "").strip()
    if ctype:
        next_params.notes = f"{ctype}. {notes}".strip() if notes else ctype
    elif notes:
        next_params.notes = notes

    positions = extracted.get("positions")
    if positions is not None:
        try:
            count = max(1, int(float(positions)))
            next_params.dimensions["pin_count"] = DimensionValue(value=count, unit="count", source="ai_extracted", confidence=ai_conf)
            rows = 2 if count > 8 else 1
            next_params.dimensions["pin_rows"] = DimensionValue(value=rows, unit="count", source="ai_extracted", confidence=ai_conf)
        except (TypeError, ValueError):
            pass

    pitch = extracted.get("pitch_mm")
    if pitch is not None:
        try:
            pv = float(pitch)
            if 0.1 <= pv <= 50:
                next_params.dimensions["pin_pitch"] = DimensionValue(value=pv, source="ai_extracted", confidence=ai_conf)
        except (TypeError, ValueError):
            pass

    def _set_len(key: str, dim_key: str) -> None:
        val = extracted.get(key)
        if val is None:
            return
        try:
            fv = float(val)
            if fv > 0:
                next_params.dimensions[dim_key] = DimensionValue(value=fv, source="ai_extracted", confidence=ai_conf)
        except (TypeError, ValueError):
            pass

    _set_len("body_length_mm", "overall_length")
    _set_len("body_width_mm", "overall_width")
    _set_len("body_height_mm", "overall_height")

    cav = extracted.get("cavity_diameter_mm")
    if cav is not None:
        try:
            cd = float(cav)
            if cd > 0:
                next_params.dimensions["pin_diameter"] = DimensionValue(
                    value=round(cd / 1.6, 4),
                    source="ai_extracted",
                    confidence=ai_conf,
                )
        except (TypeError, ValueError):
            pass

    _set_len("mounting_hole_spacing_mm", "mount_hole_spacing")
    _set_len("mounting_hole_diameter_mm", "mount_hole_diameter")

    merged_unknown = list(dict.fromkeys(next_params.unknown_fields))
    for item in extracted.get("unknown_fields") or []:
        s = str(item).strip()
        if s and s not in merged_unknown:
            merged_unknown.append(s)
    for key in (
        "positions",
        "pitch_mm",
        "body_length_mm",
        "body_width_mm",
        "body_height_mm",
        "cavity_diameter_mm",
        "mounting_hole_spacing_mm",
        "mounting_hole_diameter_mm",
    ):
        if extracted.get(key) is not None:
            continue
        internal = CAD_EXTRACT_KEY_TO_INTERNAL.get(key)
        if internal:
            dim = next_params.dimensions.get(internal)
            if dim and dim.source in {"text_hint", "user_confirmed", "ai_extracted"}:
                continue
        if key not in merged_unknown:
            merged_unknown.append(key)
    next_params.unknown_fields = merged_unknown

    if any(dim.source == "ai_extracted" for dim in next_params.dimensions.values()):
        next_params.source = "ai_extracted"  # type: ignore[assignment]

    _derive_body_from_pin_array(next_params.dimensions, overwrite_defaults=False)
    return next_params


def apply_confirmed_params(params: ConnectorCadParams, confirmed: dict[str, Any]) -> ConnectorCadParams:
    next_params = params.model_copy(deep=True)
    for key, raw_value in confirmed.items():
        target_key, unit = CAD_TO_INTERNAL.get(key, (key, next_params.dimensions.get(key, DimensionValue(value=0)).unit))
        if target_key not in next_params.dimensions:
            continue
        value = raw_value.get("value") if isinstance(raw_value, dict) else raw_value
        if value is None:
            continue
        next_params.dimensions[target_key] = DimensionValue(
            value=value,
            unit=unit,
            source="user_confirmed",
            confidence="high",
        )
    if confirmed:
        next_params.source = "user_confirmed"
    return next_params


def merge_confirmed_params(params: ConnectorCadParams, payload: dict[str, Any]) -> ConnectorCadParams:
    next_params = apply_confirmed_params(params, payload.get("confirmed_params") or payload.get("dimensions") or payload)
    accepted_unknowns = list(dict.fromkeys(payload.get("accepted_unknowns", [])))
    next_params.accepted_unknowns = accepted_unknowns
    next_params.notes = payload.get("notes")
    next_params.unknown_fields = [field for field in next_params.unknown_fields if field not in accepted_unknowns]
    if not next_params.unknown_fields:
        next_params.status = "completed"
        next_params.is_provisional = False
        next_params.warning = None
    else:
        next_params.status = "needs_confirmation"
        next_params.is_provisional = True
        next_params.warning = PROVISIONAL_WARNING
    _derive_body_from_pin_array(next_params.dimensions, overwrite_defaults=False)
    return next_params


def mark_failed(params: ConnectorCadParams, error: str) -> ConnectorCadParams:
    next_params = params.model_copy(deep=True)
    next_params.status = "failed"
    next_params.error = error
    return next_params


def apply_audit_metadata(params: ConnectorCadParams, manifest: dict[str, Any]) -> ConnectorCadParams:
    next_params = params.model_copy(deep=True)
    source_domain = manifest.get("source_domain", {})
    next_params.source_manifest = "source_manifest.json"
    next_params.source_domain_category = source_domain.get("category", "unknown")
    next_params.source_domain_approved = bool(source_domain.get("is_approved", False))
    next_params.file_hashes = {
        item.get("path"): item.get("sha256")
        for item in manifest.get("generated_files", {}).values()
        if item.get("path") and item.get("path") != "params.json" and item.get("sha256")
    }
    return next_params


def dimension_number(params: ConnectorCadParams, key: str) -> float:
    return float(params.dimensions[key].value)


def dimension_int(params: ConnectorCadParams, key: str) -> int:
    return int(params.dimensions[key].value)


def _extract_pin_count(text: str) -> int | None:
    if not text:
        return None
    array_match = re.search(r"(\d+)\s*[xX]\s*(\d+)", text)
    if array_match:
        return int(array_match.group(1)) * int(array_match.group(2))
    pin_match = re.search(r"(\d+)\s*(?:pin|pins|p|针|针位)", text, flags=re.IGNORECASE)
    if pin_match:
        return int(pin_match.group(1))
    return None


def _extract_pitch(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*mm", text, flags=re.IGNORECASE)
    if not match:
        return None
    pitch = float(match.group(1))
    return pitch if 0.5 <= pitch <= 10 else None


def _derive_body_from_pin_array(dimensions: dict[str, DimensionValue], overwrite_defaults: bool = True) -> None:
    if "pin_count" not in dimensions or "pin_rows" not in dimensions or "pin_pitch" not in dimensions:
        return
    pin_count = int(dimensions["pin_count"].value)
    rows = max(1, int(dimensions["pin_rows"].value))
    pitch = float(dimensions["pin_pitch"].value)
    columns = math.ceil(pin_count / rows)
    cavity_length = max(12.0, (columns - 1) * pitch + 8.0)
    cavity_width = 7.0 if rows == 1 else max(8.0, (rows - 1) * pitch + 6.0)
    for key, value in {"cavity_length": round(cavity_length, 2), "cavity_width": round(cavity_width, 2)}.items():
        if key in dimensions and (overwrite_defaults or dimensions[key].source == "default_mvp"):
            dimensions[key] = DimensionValue(value=value, source="text_hint", confidence="medium")
