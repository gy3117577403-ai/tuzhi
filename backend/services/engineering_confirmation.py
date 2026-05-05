from __future__ import annotations

from typing import Any


def build_engineering_confirmation_checklist(
    params: dict[str, Any],
    flat_cad: dict[str, Any],
    terminal_insertion: dict[str, Any],
    structure_report: dict[str, Any],
    image_search: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a conservative engineering checklist for SOP/WI draft release."""
    image_search = image_search or params.get("image_search") or {}
    structure = (structure_report.get("structure_completeness") or structure_report or {})
    term = terminal_insertion.get("terminal_insertion") or terminal_insertion or {}
    items = [
        _item(
            "confirm_part_number",
            "产品识别",
            "确认连接器型号是否与参考图片一致",
            "image_search.selected_part_match / user input",
            "high",
            "搜索图片可能存在相近料号或低证据命中风险。",
        ),
        _item(
            "confirm_mating_face",
            "方向判断",
            "确认正面 / 对插面判断是否正确",
            "connector_view_classification.json",
            "medium",
        ),
        _item(
            "confirm_terminal_insertion_face",
            "端子插入",
            "确认端子是否从入线面插入",
            "terminal_insertion.json",
            "high",
            f"系统 confidence={term.get('confidence') or 'unknown'}，必须人工确认。",
        ),
        _item(
            "confirm_cavity_numbering",
            "孔位编号",
            "确认 cavity 编号方向与客户图纸一致",
            "connector_2d_recipe.json",
            "high",
        ),
        _item(
            "confirm_flat_cad_dimensions",
            "尺寸",
            "确认平面 CAD 仅作为示意，不作为制造尺寸依据",
            "dimension_assumptions",
            "high",
            "平面 CAD 为视觉/工艺示意图，非原厂制造尺寸图。",
        ),
    ]

    status = str(structure.get("status") or flat_cad.get("status") or "")
    if status != "complete":
        items.append(
            _item(
                "confirm_structure_completeness",
                "结构完整性",
                "确认缺失或不完整视图是否影响 SOP/WI 使用",
                "structure_completeness_report.json",
                "high",
                "结构完整性不是 complete，需要补充工程判断。",
            )
        )

    missing = structure.get("missing_items") or flat_cad.get("missing_items") or []
    for idx, missing_item in enumerate(missing, start=1):
        items.append(
            _item(
                f"confirm_missing_item_{idx}",
                "结构完整性",
                f"确认缺失项：{missing_item}",
                "structure_completeness_report.json",
                "medium",
            )
        )

    part_match = image_search.get("selected_part_match") or {}
    evidence = image_search.get("selected_match_evidence") or {}
    generation_risk = image_search.get("generation_risk") or {}
    risk_accepted = bool(
        image_search.get("generation_risk_accepted")
        or image_search.get("part_mismatch_risk_accepted")
        or generation_risk.get("requires_confirmation")
    )
    if (
        (part_match.get("match_level") in {"near_miss", "none"})
        or (evidence.get("evidence_level") in {"low", "unknown"})
        or risk_accepted
    ):
        items.append(
            _item(
                "confirm_image_search_risk",
                "图片来源风险",
                "确认搜索图片风险已被工程人员接受",
                "image_search.selected_part_match / selected_match_evidence / generation_risk",
                "high",
                "存在相近料号、低证据或用户已确认风险的候选图。",
            )
        )

    required_count = sum(1 for item in items if item["required"])
    pending_count = sum(1 for item in items if item["status"] == "pending")
    high_risk_count = sum(1 for item in items if item["risk_level"] == "high")
    return {
        "checklist_type": "engineering_confirmation_checklist",
        "status": "requires_confirmation",
        "items": items,
        "summary": {
            "required_count": required_count,
            "pending_count": pending_count,
            "high_risk_count": high_risk_count,
            "can_release_to_shopfloor": False,
            "release_condition": "All required items must be confirmed by engineering/process/quality.",
        },
        "warnings": [
            "This checklist must be reviewed before SOP/WI release.",
            "This is a SOP/WI draft package only; it is not released for shopfloor use.",
        ],
    }


def _item(
    item_id: str,
    category: str,
    label: str,
    basis: str,
    risk_level: str,
    note: str = "",
) -> dict[str, Any]:
    return {
        "id": item_id,
        "category": category,
        "label": label,
        "required": True,
        "status": "pending",
        "basis": basis,
        "risk_level": risk_level,
        "note": note,
    }
