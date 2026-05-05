from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.engineering_confirmation import build_engineering_confirmation_checklist
from services.sop_wi_generator import build_sop_wi_draft

SOP_FILES = {
    "draft_json": "sop_wi_draft.json",
    "draft_html": "sop_wi_draft.html",
    "summary_md": "sop_wi_summary.md",
    "confirmation_checklist": "engineering_confirmation_checklist.json",
    "assets_manifest": "sop_wi_assets_manifest.json",
}


def export_sop_wi_package(job_id: str, output_dir: str | Path, params_override: dict[str, Any] | None = None) -> dict[str, Any]:
    out = Path(output_dir)
    params = params_override or _read_json(out / "params.json")
    flat_cad = params.get("flat_cad") or {}
    if not flat_cad.get("enabled"):
        raise ValueError("flat_cad is required before SOP/WI draft export")

    selected_image = _read_json_optional(out / "selected_image.json")
    image_features = _read_json_optional(out / "image_features.json")
    visual_recipe = _read_json_optional(out / "visual_recipe.json") or params.get("visual_recipe") or {}
    terminal_insertion = _read_json_optional(out / "terminal_insertion.json")
    structure_report = _read_json_optional(out / "structure_completeness_report.json")
    image_search_results = _read_json_optional(out / "image_search_results.json")

    checklist = build_engineering_confirmation_checklist(
        params=params,
        flat_cad=flat_cad,
        terminal_insertion=terminal_insertion or {},
        structure_report=structure_report or {},
        image_search=params.get("image_search") or image_search_results or {},
    )
    draft = build_sop_wi_draft(
        job_id=job_id,
        params=params,
        flat_cad_files=flat_cad.get("files") or {},
        selected_image=selected_image,
        image_features=image_features,
        visual_recipe=visual_recipe,
        terminal_insertion=terminal_insertion,
        structure_report=structure_report,
        confirmation_checklist=checklist,
    )

    manifest = _build_manifest(job_id, out, flat_cad, selected_image, image_search_results)
    _write_json(out / SOP_FILES["confirmation_checklist"], checklist)
    _write_json(out / SOP_FILES["draft_json"], draft)
    _write_json(out / SOP_FILES["assets_manifest"], manifest)
    (out / SOP_FILES["draft_html"]).write_text(_render_html(draft, checklist, out), encoding="utf-8")
    (out / SOP_FILES["summary_md"]).write_text(_render_markdown(draft, checklist, manifest), encoding="utf-8")

    sop_wi = {
        "enabled": True,
        "status": "draft_requires_engineering_confirmation",
        "files": dict(SOP_FILES),
        "readiness": {
            "status": draft.get("readiness", {}).get("status") or "caution",
            "can_release_to_shopfloor": False,
            "manual_confirmation_required": True,
        },
        "checklist_summary": checklist.get("summary") or {},
        "warnings": [
            "SOP/WI draft requires engineering confirmation before release.",
            "Flat CAD views are inferred visual aids, not official manufacturer drawings.",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _update_params_json(out / "params.json", sop_wi)
    return {"ok": True, "sop_wi": sop_wi, "paths": {name: out / filename for name, filename in SOP_FILES.items()}}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_optional(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return _read_json(path)
    except Exception:
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _update_params_json(path: Path, sop_wi: dict[str, Any]) -> None:
    if not path.exists():
        return
    params = _read_json(path)
    params["sop_wi"] = sop_wi
    path.write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_manifest(
    job_id: str,
    out: Path,
    flat_cad: dict[str, Any],
    selected_image: dict[str, Any] | None,
    image_search_results: dict[str, Any] | None,
) -> dict[str, Any]:
    filenames = [
        "sop_wi_draft.json",
        "sop_wi_draft.html",
        "sop_wi_summary.md",
        "engineering_confirmation_checklist.json",
        "sop_wi_assets_manifest.json",
        "connector_flat_views.svg",
        "connector_front_view.dxf",
        "connector_rear_view.dxf",
        "connector_top_view.dxf",
        "connector_side_view.dxf",
        "connector_insertion_direction.dxf",
        "terminal_insertion.json",
        "structure_completeness_report.json",
        "selected_image.json",
        "image_search_results.json",
    ]
    assets = []
    for filename in filenames:
        path = out / filename
        assets.append(
            {
                "filename": filename,
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else 0,
                "purpose": _asset_purpose(filename),
            }
        )
    return {
        "manifest_type": "sop_wi_assets_manifest",
        "job_id": job_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "assets": assets,
        "flat_cad_files": flat_cad.get("files") or {},
        "selected_image_source": (selected_image or {}).get("selected", {}).get("source_url", ""),
        "image_search_provider": (image_search_results or {}).get("provider", ""),
        "warnings": ["Assets are for SOP/WI draft review only."],
    }


def _asset_purpose(filename: str) -> str:
    if filename.endswith(".dxf"):
        return "flat CAD engineering view"
    if filename.endswith(".svg"):
        return "printable flat view preview"
    if filename.endswith(".html"):
        return "printable SOP/WI draft"
    if filename.endswith(".md"):
        return "quick SOP/WI summary"
    return "supporting JSON data"


def _render_html(draft: dict[str, Any], checklist: dict[str, Any], out: Path) -> str:
    svg = ""
    svg_path = out / "connector_flat_views.svg"
    if svg_path.exists():
        svg = svg_path.read_text(encoding="utf-8", errors="replace")
    sections = "\n".join(_render_section(section) for section in draft.get("sections", []))
    checklist_rows = "\n".join(
        "<tr>"
        f"<td>{_e(item.get('category'))}</td>"
        f"<td>{_e(item.get('label'))}</td>"
        f"<td>{_e(item.get('risk_level'))}</td>"
        f"<td>{_e(item.get('status'))}</td>"
        f"<td>{_e(item.get('basis'))}</td>"
        "</tr>"
        for item in checklist.get("items", [])
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>连接器装配作业指导草稿</title>
  <style>
    @page {{ size: A4; margin: 14mm; }}
    body {{ font-family: Arial, 'Microsoft YaHei', sans-serif; color: #111827; line-height: 1.45; }}
    h1 {{ margin: 0 0 6px; font-size: 24px; }}
    h2 {{ margin: 20px 0 8px; font-size: 16px; border-bottom: 1px solid #d1d5db; padding-bottom: 4px; }}
    .doc-status {{ color: #9a3412; font-weight: 700; }}
    .warning {{ border: 2px solid #c2410c; background: #fff7ed; color: #7c2d12; padding: 10px 12px; margin: 12px 0; font-weight: 700; }}
    .svg-wrap {{ border: 1px solid #d1d5db; padding: 8px; margin: 10px 0; overflow: auto; }}
    .svg-wrap svg {{ max-width: 100%; height: auto; }}
    table {{ width: 100%; border-collapse: collapse; margin: 8px 0 16px; font-size: 12px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 6px 7px; vertical-align: top; }}
    th {{ background: #f3f4f6; text-align: left; }}
    .signoff td {{ height: 42px; }}
    .footer {{ margin-top: 20px; color: #6b7280; font-size: 11px; }}
  </style>
</head>
<body>
  <h1>连接器装配作业指导草稿</h1>
  <div class="doc-status">状态：草稿，必须经工程、工艺、品质确认后才能下发车间。</div>
  <div class="warning">本文件为 SOP/WI 草稿。平面 CAD 为非原厂制造尺寸图，仅用于工艺示意、SOP、WI、端子插入方向参考，不可直接作为制造尺寸依据。</div>
  <h2>平面 CAD 四视图</h2>
  <div class="svg-wrap">{svg}</div>
  {sections}
  <h2>工程确认清单</h2>
  <table>
    <thead><tr><th>类别</th><th>确认项</th><th>风险</th><th>状态</th><th>依据</th></tr></thead>
    <tbody>{checklist_rows}</tbody>
  </table>
  <h2>签核栏</h2>
  <table class="signoff">
    <tr><th>编制</th><th>工艺</th><th>品质</th><th>工程批准</th></tr>
    <tr><td></td><td></td><td></td><td></td></tr>
    <tr><th>日期</th><th>日期</th><th>日期</th><th>日期</th></tr>
    <tr><td></td><td></td><td></td><td></td></tr>
  </table>
  <div class="footer">禁止声明：不得将本草稿视为原厂 CAD、正式工艺文件或制造级尺寸依据。</div>
</body>
</html>
"""


def _render_section(section: dict[str, Any]) -> str:
    rows = "\n".join(
        f"<tr><th>{_e(item.get('label'))}</th><td>{_e(_value_to_text(item.get('value')))}</td></tr>"
        for item in section.get("items", [])
    )
    return f"<h2>{_e(section.get('title'))}</h2><table><tbody>{rows}</tbody></table>"


def _render_markdown(draft: dict[str, Any], checklist: dict[str, Any], manifest: dict[str, Any]) -> str:
    summary = checklist.get("summary") or {}
    lines = [
        "# SOP/WI 草稿摘要",
        "",
        f"- job_id: `{draft.get('job_id')}`",
        f"- status: `{draft.get('status')}`",
        f"- model_origin: `{draft.get('model_origin')}`",
        "- readiness: `caution`，可作为 SOP/WI 草稿基础，需工程确认后使用。",
        "- can_release_to_shopfloor: `false`",
        "",
        "## 待确认项",
    ]
    for item in checklist.get("items", []):
        lines.append(f"- [{item.get('risk_level')}] {item.get('category')}: {item.get('label')} ({item.get('status')})")
    lines.extend(
        [
            "",
            "## 统计",
            f"- required_count: {summary.get('required_count')}",
            f"- pending_count: {summary.get('pending_count')}",
            f"- high_risk_count: {summary.get('high_risk_count')}",
            "",
            "## 文件",
        ]
    )
    for asset in manifest.get("assets", []):
        lines.append(f"- {asset.get('filename')}: {'ok' if asset.get('exists') else 'missing'}")
    lines.extend(["", "## 禁用声明", "- 非原厂制造尺寸图，不可直接作为制造尺寸依据，不可直接下发车间。"])
    return "\n".join(lines) + "\n"


def _value_to_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)
