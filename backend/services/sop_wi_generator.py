from __future__ import annotations

from typing import Any


SOP_WARNINGS = [
    "本文件为 AI/视觉生成的 SOP/WI 草稿，需工程确认后使用。",
    "平面 CAD 为工艺示意图，不代表原厂制造尺寸图。",
    "不得作为制造级尺寸依据，不得直接下发车间。",
]


def build_sop_wi_draft(
    job_id: str,
    params: dict[str, Any],
    flat_cad_files: dict[str, str],
    selected_image: dict[str, Any] | None = None,
    image_features: dict[str, Any] | None = None,
    visual_recipe: dict[str, Any] | None = None,
    terminal_insertion: dict[str, Any] | None = None,
    structure_report: dict[str, Any] | None = None,
    confirmation_checklist: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected = selected_image or {}
    selected_meta = selected.get("selected") or selected
    terminal = (terminal_insertion or {}).get("terminal_insertion") or terminal_insertion or {}
    structure = (structure_report or {}).get("structure_completeness") or structure_report or {}
    recipe = visual_recipe or params.get("visual_recipe") or {}
    checklist = confirmation_checklist or {}
    image_search = params.get("image_search") or {}

    return {
        "document_type": "sop_wi_draft",
        "job_id": job_id,
        "title": "连接器装配作业指导草稿",
        "status": "draft_requires_engineering_confirmation",
        "model_origin": params.get("model_origin"),
        "part_number": params.get("part_number"),
        "readiness": {
            "status": "caution" if structure.get("status") != "insufficient" else "no",
            "can_release_to_shopfloor": False,
            "manual_confirmation_required": True,
        },
        "sections": [
            {
                "id": "product_identification",
                "title": "1. 产品识别信息",
                "items": [
                    _kv("job_id", job_id),
                    _kv("part_number", params.get("part_number")),
                    _kv("model_origin", params.get("model_origin")),
                    _kv("manufacturing_accuracy", params.get("manufacturing_accuracy") or "visual_proxy_only"),
                    _kv("status", "草稿，待工程确认"),
                ],
            },
            {
                "id": "reference_image",
                "title": "2. 参考图片与来源",
                "items": [
                    _kv("title", selected_meta.get("title")),
                    _kv("image_url", selected_meta.get("image_url")),
                    _kv("source_url", selected_meta.get("source_url") or params.get("source_url")),
                    _kv("domain", selected_meta.get("domain")),
                    _kv("part_match", (image_search.get("selected_part_match") or selected_meta.get("part_match") or {}).get("match_level")),
                    _kv("evidence", (image_search.get("selected_match_evidence") or selected_meta.get("match_evidence") or {}).get("evidence_level")),
                    _kv("generation_risk_accepted", image_search.get("generation_risk_accepted")),
                ],
            },
            {
                "id": "flat_cad_views",
                "title": "3. 平面 CAD 视图",
                "items": [
                    _kv("front_mating_face", flat_cad_files.get("front_view_dxf")),
                    _kv("rear_wire_entry_face", flat_cad_files.get("rear_view_dxf")),
                    _kv("top_view", flat_cad_files.get("top_view_dxf")),
                    _kv("side_view", flat_cad_files.get("side_view_dxf")),
                    _kv("insertion_direction", flat_cad_files.get("insertion_direction_dxf")),
                    _kv("svg_overview", flat_cad_files.get("flat_views_svg")),
                    _kv("disclaimer", "非原厂制造尺寸图，仅作为工艺示意。"),
                ],
            },
            {
                "id": "terminal_insertion",
                "title": "4. 端子插入方向",
                "items": [
                    _kv("recommended_insertion_face", terminal.get("recommended_insertion_face")),
                    _kv("opposite_mating_face", terminal.get("opposite_mating_face")),
                    _kv("insertion_direction", terminal.get("insertion_direction")),
                    _kv("view_for_work_instruction", terminal.get("view_for_work_instruction")),
                    _kv("view_for_pin_check", terminal.get("view_for_pin_check")),
                    _kv("confidence", terminal.get("confidence")),
                    _kv("requires_manual_confirmation", terminal.get("requires_manual_confirmation", True)),
                ],
            },
            {
                "id": "cavity_map",
                "title": "5. 孔位 / cavity map",
                "items": [
                    _kv("cavity_array", recipe.get("cavity_array")),
                    _kv("cavity_numbering", "待工程确认孔位编号方向与客户图纸一致"),
                ],
            },
            {
                "id": "qc_checkpoints",
                "title": "6. QC 检查重点",
                "items": [
                    _kv("front_face_check", "核对正面/对插面孔位、定位键、锁扣方向"),
                    _kv("rear_face_check", "核对入线面、端子插入方向、线束出口方向"),
                    _kv("dimension_check", "尺寸仅为示意，关键尺寸须按客户图纸或实物确认"),
                    _kv("structure_completeness", structure.get("status")),
                    _kv("structure_score", structure.get("score")),
                ],
            },
            {
                "id": "engineering_confirmation",
                "title": "7. 工程确认清单",
                "items": [
                    _kv(item.get("id"), f"{item.get('category')} / {item.get('label')} / {item.get('risk_level')}")
                    for item in checklist.get("items", [])
                ],
            },
            {
                "id": "release_signoff",
                "title": "8. 签核栏",
                "items": [
                    _kv("编制", "姓名 / 日期"),
                    _kv("工艺", "姓名 / 日期"),
                    _kv("品质", "姓名 / 日期"),
                    _kv("工程批准", "姓名 / 日期"),
                ],
            },
        ],
        "warnings": SOP_WARNINGS,
    }


def _kv(label: str | None, value: Any) -> dict[str, Any]:
    return {"label": label or "", "value": value if value is not None else ""}
