from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import cadquery as cq
from cadquery import exporters

from services.connector_params import PARAMETRIC_DISCLAIMER, PROVISIONAL_WARNING, ConnectorCadParams, dimension_int, dimension_number

DEFAULT_CAD_PARAMS = {
    "positions": 2,
    "pitch_mm": 6.0,
    "body_length_mm": 36.0,
    "body_width_mm": 18.0,
    "body_height_mm": 14.0,
    "cavity_diameter_mm": 3.2,
    "mounting_hole_diameter_mm": 3.0,
    "mounting_hole_spacing_mm": 28.0,
}

def generate_connector_cad(params: dict[str, Any] | ConnectorCadParams, output_dir: str | Path) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    normalized = normalize_cad_params(params)
    model = build_parametric_connector(normalized)

    step_path = output_path / "model.step"
    stl_path = output_path / "model.stl"
    dxf_path = output_path / "drawing.dxf"
    params_path = output_path / "params.json"

    exporters.export(model, str(step_path), exportType="STEP")
    exporters.export(model, str(stl_path), exportType="STL")
    write_engineering_dxf(normalized, dxf_path)
    write_params_json(params, normalized, params_path)

    return {
        "model.step": step_path,
        "model.stl": stl_path,
        "drawing.dxf": dxf_path,
        "params.json": params_path,
    }


def build_connector(params: ConnectorCadParams) -> cq.Workplane:
    return build_parametric_connector(normalize_cad_params(params))


def normalize_cad_params(params: dict[str, Any] | ConnectorCadParams) -> dict[str, Any]:
    if isinstance(params, ConnectorCadParams):
        normalized = {
            "part_number": params.title,
            "positions": dimension_int(params, "pin_count"),
            "pitch_mm": dimension_number(params, "pin_pitch"),
            "body_length_mm": dimension_number(params, "overall_length"),
            "body_width_mm": dimension_number(params, "overall_width"),
            "body_height_mm": dimension_number(params, "overall_height"),
            "cavity_diameter_mm": dimension_number(params, "pin_diameter") * 1.6,
            "mounting_hole_diameter_mm": dimension_number(params, "mount_hole_diameter"),
            "mounting_hole_spacing_mm": dimension_number(params, "mount_hole_spacing"),
            "input_source": params.source,
            "model_origin": params.model_origin,
            "source_type": params.source_type,
            "official_candidate_found": params.official_candidate_found,
            "official_cad_downloaded": params.official_cad_downloaded,
            "fallback_reason": params.fallback_reason,
            "source_url": params.source_url,
            "cad_url": params.cad_url,
            "license_note": params.license_note,
            "registry_item_id": params.registry_item_id,
            "registry_candidate_id": params.registry_candidate_id,
            "registry_status": params.registry_status,
            "revision": params.revision,
            "version_label": params.version_label,
            "registry_sha256": params.registry_sha256,
            "registry_cache_status": params.registry_cache_status,
            "cached_file_used": params.cached_file_used,
            "cached_file_sha256": params.cached_file_sha256,
            "cache_metadata_path": params.cache_metadata_path,
            "cached_at": params.cached_at,
            "selection_reason": params.selection_reason,
            "available_versions": params.available_versions,
            "preferred_revision": params.preferred_revision,
            "preferred_version_label": params.preferred_version_label,
            "status": params.status,
            "is_provisional": params.is_provisional,
            "warning": params.warning,
            "accepted_unknowns": params.accepted_unknowns,
            "notes": params.notes,
            "unknown_fields": params.unknown_fields,
            "ai_extraction": params.ai_extraction,
            "template_name": params.template_name,
            "appearance_confidence": params.appearance_confidence,
            "visual_match": params.visual_match,
            "preview_style": params.preview_style,
            "appearance_pipeline": params.appearance_pipeline,
            "image_feature_summary": params.image_feature_summary,
            "vision_report_summary": params.vision_report_summary,
            "image_fallback_warning": params.image_fallback_warning,
            "dimension_meta": {
                "positions": params.dimensions["pin_count"],
                "pitch_mm": params.dimensions["pin_pitch"],
                "body_length_mm": params.dimensions["overall_length"],
                "body_width_mm": params.dimensions["overall_width"],
                "body_height_mm": params.dimensions["overall_height"],
                "cavity_diameter_mm": params.dimensions["pin_diameter"],
                "mounting_hole_diameter_mm": params.dimensions["mount_hole_diameter"],
                "mounting_hole_spacing_mm": params.dimensions["mount_hole_spacing"],
            },
        }
    else:
        normalized = dict(params)

    for key, value in DEFAULT_CAD_PARAMS.items():
        normalized.setdefault(key, value)

    normalized["positions"] = max(1, int(normalized["positions"]))
    normalized["pitch_mm"] = float(normalized["pitch_mm"])
    normalized["body_length_mm"] = float(normalized["body_length_mm"])
    normalized["body_width_mm"] = float(normalized["body_width_mm"])
    normalized["body_height_mm"] = float(normalized["body_height_mm"])
    normalized["cavity_diameter_mm"] = float(normalized["cavity_diameter_mm"])
    normalized["mounting_hole_diameter_mm"] = float(normalized["mounting_hole_diameter_mm"])
    normalized["mounting_hole_spacing_mm"] = float(normalized["mounting_hole_spacing_mm"])
    normalized.setdefault("part_number", "MVP-CONNECTOR")
    normalized.setdefault("input_source", "default_mvp")
    normalized.setdefault("model_origin", "generic_mvp")
    normalized.setdefault("source_type", "not_found")
    normalized.setdefault("official_candidate_found", False)
    normalized.setdefault("official_cad_downloaded", False)
    normalized.setdefault("fallback_reason", None)
    normalized.setdefault("source_url", "")
    normalized.setdefault("cad_url", "")
    normalized.setdefault("license_note", "User should verify manufacturer CAD terms before production use.")
    normalized.setdefault("registry_item_id", None)
    normalized.setdefault("registry_candidate_id", None)
    normalized.setdefault("registry_status", None)
    normalized.setdefault("revision", None)
    normalized.setdefault("version_label", None)
    normalized.setdefault("registry_sha256", None)
    normalized.setdefault("registry_cache_status", None)
    normalized.setdefault("cached_file_used", False)
    normalized.setdefault("cached_file_sha256", None)
    normalized.setdefault("cache_metadata_path", None)
    normalized.setdefault("cached_at", None)
    normalized.setdefault("selection_reason", None)
    normalized.setdefault("available_versions", [])
    normalized.setdefault("preferred_revision", None)
    normalized.setdefault("preferred_version_label", None)
    normalized.setdefault("status", "needs_confirmation")
    normalized.setdefault("is_provisional", normalized["status"] != "completed")
    normalized.setdefault("warning", PROVISIONAL_WARNING if normalized["is_provisional"] else None)
    normalized.setdefault("accepted_unknowns", [])
    normalized.setdefault("notes", None)
    normalized.setdefault("unknown_fields", ["official_step_source", "manufacturer_exact_dimensions", "tolerance", "material"])
    normalized.setdefault("ai_extraction", None)
    normalized.setdefault("template_name", None)
    normalized.setdefault("appearance_confidence", None)
    normalized.setdefault("visual_match", None)
    normalized.setdefault("preview_style", None)
    normalized.setdefault("appearance_pipeline", None)
    normalized.setdefault("image_feature_summary", None)
    normalized.setdefault("vision_report_summary", None)
    normalized.setdefault("image_fallback_warning", None)
    return normalized


def build_parametric_connector(params: dict[str, Any]) -> cq.Workplane:
    length = params["body_length_mm"]
    width = params["body_width_mm"]
    height = params["body_height_mm"]
    edge_radius = min(1.0, width * 0.08, height * 0.08)
    chamfer = min(0.45, height * 0.05)

    body = (
        cq.Workplane("XY")
        .box(length, width, height)
        .edges("|Z")
        .fillet(edge_radius)
        .edges("#Z")
        .chamfer(chamfer)
    )

    front_pocket_depth = min(4.2, height * 0.36)
    front_pocket = (
        cq.Workplane("XY")
        .box(length * 0.58, width * 0.52, front_pocket_depth)
        .translate((0, 0, height / 2 - front_pocket_depth / 2 + 0.05))
    )
    model = body.cut(front_pocket)

    cavity_depth = front_pocket_depth + 0.8
    for x, y in cavity_positions(params):
        cavity = (
            cq.Workplane("XY")
            .circle(params["cavity_diameter_mm"] / 2)
            .extrude(cavity_depth)
            .translate((x, y, height / 2 - cavity_depth + 0.05))
        )
        model = model.cut(cavity)

    lock_width = min(length * 0.42, 16.0)
    lock_depth = min(width * 0.18, 3.0)
    lock_height = min(height * 0.22, 3.0)
    lock = (
        cq.Workplane("XY")
        .box(lock_width, lock_depth, lock_height)
        .translate((0, width / 2 + lock_depth / 2 - 0.25, height / 2 + lock_height / 2 - 0.2))
        .edges("|Z")
        .fillet(0.25)
    )
    model = model.union(lock)

    mount_radius = params["mounting_hole_diameter_mm"] / 2
    for x in (-params["mounting_hole_spacing_mm"] / 2, params["mounting_hole_spacing_mm"] / 2):
        mount_hole = cq.Workplane("XY").circle(mount_radius).extrude(height + 1.0).translate((x, 0, -0.5))
        model = model.cut(mount_hole)

    return model


def cavity_positions(params: dict[str, Any]) -> list[tuple[float, float]]:
    positions = params["positions"]
    pitch = params["pitch_mm"]
    columns = positions
    if positions > 8 and positions % 2 == 0:
        rows = 2
        columns = math.ceil(positions / rows)
    else:
        rows = 1

    coords: list[tuple[float, float]] = []
    for index in range(positions):
        row = index // columns
        column = index % columns
        x = (column - (columns - 1) / 2) * pitch
        y = (row - (rows - 1) / 2) * pitch
        coords.append((x, y))
    return coords


def pin_positions(params: ConnectorCadParams) -> list[tuple[float, float]]:
    return cavity_positions(normalize_cad_params(params))


def write_params_json(original_params: dict[str, Any] | ConnectorCadParams, params: dict[str, Any], path: Path) -> None:
    dimension_keys = [
        "positions",
        "pitch_mm",
        "body_length_mm",
        "body_width_mm",
        "body_height_mm",
        "cavity_diameter_mm",
        "mounting_hole_diameter_mm",
        "mounting_hole_spacing_mm",
    ]
    dimension_meta = params.get("dimension_meta", {})
    payload = {
        "part_number": params.get("part_number", "MVP-CONNECTOR"),
        "model_type": "parametric_mvp_connector",
        "is_provisional": params.get("is_provisional", True),
        "status": params.get("status", "needs_confirmation"),
        "unit": "mm",
        "source": params.get("input_source", "default_mvp"),
        "model_origin": params.get("model_origin", "generic_mvp"),
        "source_type": params.get("source_type", "not_found"),
        "official_candidate_found": params.get("official_candidate_found", False),
        "official_cad_downloaded": params.get("official_cad_downloaded", False),
        "fallback_reason": params.get("fallback_reason"),
        "source_url": params.get("source_url", ""),
        "cad_url": params.get("cad_url", ""),
        "license_note": params.get("license_note", "User should verify manufacturer CAD terms before production use."),
        "registry_item_id": params.get("registry_item_id"),
        "registry_candidate_id": params.get("registry_candidate_id"),
        "registry_status": params.get("registry_status"),
        "revision": params.get("revision"),
        "version_label": params.get("version_label"),
        "registry_sha256": params.get("registry_sha256"),
        "registry_cache_status": params.get("registry_cache_status"),
        "cached_file_used": params.get("cached_file_used", False),
        "cached_file_sha256": params.get("cached_file_sha256"),
        "cache_metadata_path": params.get("cache_metadata_path"),
        "cached_at": params.get("cached_at"),
        "selection_reason": params.get("selection_reason"),
        "available_versions": params.get("available_versions", []),
        "preferred_revision": params.get("preferred_revision"),
        "preferred_version_label": params.get("preferred_version_label"),
        "source_manifest": params.get("source_manifest", "source_manifest.json"),
        "source_domain_category": params.get("source_domain_category"),
        "source_domain_approved": params.get("source_domain_approved"),
        "file_hashes": params.get("file_hashes", {}),
        "disclaimer": PARAMETRIC_DISCLAIMER,
        "warning": params.get("warning"),
        "dimensions": {
            key: _dimension_payload(key, params, dimension_meta)
            for key in dimension_keys
        },
        "unknown_fields": params.get("unknown_fields", []),
        "accepted_unknowns": params.get("accepted_unknowns", []),
        "notes": params.get("notes"),
        "generation_files": {
            "step": "model.step",
            "stl": "model.stl",
            "dxf": "drawing.dxf",
        },
        "ai_extraction": params.get("ai_extraction"),
        "template_name": params.get("template_name"),
        "appearance_confidence": params.get("appearance_confidence"),
        "visual_match": params.get("visual_match"),
        "preview_style": params.get("preview_style"),
        "appearance_pipeline": params.get("appearance_pipeline"),
        "image_fallback_warning": params.get("image_fallback_warning"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _dimension_payload(key: str, params: dict[str, Any], dimension_meta: dict[str, Any]) -> dict[str, Any]:
    meta = dimension_meta.get(key)
    if meta is not None:
        if hasattr(meta, "model_dump"):
            dumped = meta.model_dump()
        elif isinstance(meta, dict):
            dumped = meta
        else:
            dumped = {}
        return {
            "value": params[key],
            "unit": dumped.get("unit", "count" if key == "positions" else "mm"),
            "source": dumped.get("source", params.get("input_source", "default_mvp")),
            "confidence": dumped.get("confidence", "medium"),
        }
    return {
        "value": params[key],
        "unit": "count" if key == "positions" else "mm",
        "source": params.get("input_source", "default_mvp"),
        "confidence": "medium" if params.get("input_source") == "default_mvp" else "high",
    }


def write_engineering_dxf(params: dict[str, Any], path: Path) -> None:
    length = params["body_length_mm"]
    width = params["body_width_mm"]
    pocket_length = length * 0.58
    pocket_width = width * 0.52
    entities: list[str] = []
    entities.extend(_rect(-length / 2, -width / 2, length / 2, width / 2, "BODY"))
    entities.extend(_rect(-pocket_length / 2, -pocket_width / 2, pocket_length / 2, pocket_width / 2, "FRONT_SOCKET"))

    for x, y in cavity_positions(params):
        entities.extend(_circle(x, y, params["cavity_diameter_mm"] / 2, "CAVITIES"))

    for x in (-params["mounting_hole_spacing_mm"] / 2, params["mounting_hole_spacing_mm"] / 2):
        entities.extend(_circle(x, 0, params["mounting_hole_diameter_mm"] / 2, "MOUNTING"))

    path.write_text(
        "\n".join(["0", "SECTION", "2", "ENTITIES", *entities, "0", "ENDSEC", "0", "EOF", ""]),
        encoding="utf-8",
    )


def _rect(left: float, bottom: float, right: float, top: float, layer: str) -> list[str]:
    return [
        *_line(left, bottom, right, bottom, layer),
        *_line(right, bottom, right, top, layer),
        *_line(right, top, left, top, layer),
        *_line(left, top, left, bottom, layer),
    ]


def _line(x1: float, y1: float, x2: float, y2: float, layer: str) -> list[str]:
    return ["0", "LINE", "8", layer, "10", f"{x1:.3f}", "20", f"{y1:.3f}", "11", f"{x2:.3f}", "21", f"{y2:.3f}"]


def _circle(x: float, y: float, radius: float, layer: str) -> list[str]:
    return ["0", "CIRCLE", "8", layer, "10", f"{x:.3f}", "20", f"{y:.3f}", "40", f"{radius:.3f}"]
