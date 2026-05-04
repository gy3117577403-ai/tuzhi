from __future__ import annotations

import re
from typing import Any

from services.cad_registry import find_approved_cad_source

KNOWN_CAD_SOURCES: dict[str, dict[str, Any]] = {
    "TE 282104-1": {
        "manufacturer": "TE Connectivity",
        "part_number": "282104-1",
        "source_type": "official_candidate",
        "cad_url": "",
        "source_url": "",
        "file_type": "step",
        "confidence": "manual_pending",
        "requires_manual_url": True,
        "license_note": "User should verify manufacturer CAD terms before production use.",
    },
    "LOCAL SAMPLE STEP": {
        "manufacturer": "Test",
        "part_number": "LOCAL SAMPLE STEP",
        "source_type": "official_cad",
        "cad_url": "file://backend/test_assets/sample_official.step",
        "source_url": "local-test",
        "file_type": "step",
        "confidence": "high",
        "requires_manual_url": False,
        "license_note": "Local test asset only. User should verify manufacturer CAD terms before production use.",
    },
}


class CadSourceResolver:
    def resolve(
        self,
        part_number: str | None = None,
        manufacturer: str | None = None,
        text: str | None = None,
        preferred_revision: str | None = None,
        preferred_version_label: str | None = None,
    ) -> dict[str, Any]:
        registry_source = find_approved_cad_source(
            manufacturer=manufacturer,
            part_number=part_number,
            text=text,
            preferred_revision=preferred_revision,
            preferred_version_label=preferred_version_label,
        )
        if registry_source:
            return registry_source

        haystack = " ".join(item for item in [manufacturer, part_number, text] if item).upper()
        normalized = _normalize(haystack)
        for key, source in KNOWN_CAD_SOURCES.items():
            key_normalized = _normalize(key)
            part_normalized = _normalize(str(source.get("part_number", "")))
            if key_normalized in normalized or (part_normalized and part_normalized in normalized):
                return dict(source)
        return {
            "source_type": "not_found",
            "confidence": "low",
            "fallback": "parametric_mvp",
            "license_note": "User should verify manufacturer CAD terms before production use.",
        }


def _normalize(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()
