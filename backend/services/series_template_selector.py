from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SERIES_PATH = Path(__file__).resolve().parents[1] / "data" / "series_template_registry.json"


@dataclass
class TemplateSelection:
    template_name: str
    selection_reason: str
    confidence: str
    color: str | None
    appearance_tags: list[str]


def _load_series() -> dict[str, Any]:
    if not _SERIES_PATH.exists():
        return {"templates": []}
    return json.loads(_SERIES_PATH.read_text(encoding="utf-8"))


def _template_ids() -> set[str]:
    return {t.get("id") for t in _load_series().get("templates", []) if t.get("id")}


def _lower(s: str) -> str:
    return (s or "").lower()


def select_template(
    *,
    visual_registry_item: dict[str, Any] | None,
    ai_extracted: dict[str, Any] | None,
    user_text: str | None,
    positions_hint: int | None,
) -> TemplateSelection:
    """
    Choose series template from registry hit, AI hints, and heuristics.
    Falls back to GENERIC_RECTANGULAR_CONNECTOR.
    """
    ids = _template_ids()
    ai = ai_extracted or {}
    text = _lower(user_text or "")
    pos = positions_hint
    if isinstance(pos, str):
        try:
            pos = int(float(pos))
        except (TypeError, ValueError):
            pos = None

    if visual_registry_item and visual_registry_item.get("series"):
        series = str(visual_registry_item["series"])
        if series in ids:
            return TemplateSelection(
                template_name=series,
                selection_reason=f"Matched part visual registry entry (series={series}).",
                confidence="high",
                color=visual_registry_item.get("color"),
                appearance_tags=list(visual_registry_item.get("appearance_tags") or []),
            )
        return TemplateSelection(
            template_name="GENERIC_RECTANGULAR_CONNECTOR",
            selection_reason=f"Registry series '{series}' not in series_template_registry; using generic.",
            confidence="low",
            color="grey",
            appearance_tags=["rectangular_housing"],
        )

    ctype = _lower(str(ai.get("connector_type") or ""))
    fam = _lower(str(ai.get("manufacturer") or ""))
    notes = _lower(str(ai.get("notes") or ""))

    if "superseal" in ctype or "superseal" in text or "superseal" in notes:
        return TemplateSelection(
            template_name="TE_SUPERSEAL_2P_STYLE",
            selection_reason="AI / text suggests automotive Superseal-style family.",
            confidence="medium",
            color="black",
            appearance_tags=["automotive_2cavity", "seal_lip", "top_latch_tab"],
        )

    if pos == 2 and ("automotive" in text or "vehicle" in text or "汽车" in (user_text or "")):
        return TemplateSelection(
            template_name="TE_SUPERSEAL_2P_STYLE",
            selection_reason="2-position count + automotive context heuristic.",
            confidence="low",
            color="black",
            appearance_tags=["automotive_2cavity", "seal_lip", "top_latch_tab"],
        )

    if "blue" in ctype or "multi" in ctype or "cavity" in ctype:
        return TemplateSelection(
            template_name="TE_BLUE_MULTI_CAVITY",
            selection_reason="AI connector_type / notes suggest multi-cavity blue series.",
            confidence="low",
            color="blue",
            appearance_tags=[
                "rectangular_housing",
                "multi_cavity_front_face",
                "top_dual_guide_rails",
            ],
        )

    return TemplateSelection(
        template_name="GENERIC_RECTANGULAR_CONNECTOR",
        selection_reason="No registry hit and no strong series signals — upgraded generic rectangular template.",
        confidence="low",
        color="grey",
        appearance_tags=["rectangular_housing", "standard_pin_field"],
    )
