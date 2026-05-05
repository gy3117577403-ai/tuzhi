from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.confirmation_status import load_confirmation_status

SIGNED_FILES = {
    "signed_html": "sop_wi_signed.html",
    "signed_json": "sop_wi_signed.json",
    "signed_summary_md": "sop_wi_signed_summary.md",
}


def export_signed_sop_wi(output_dir: str | Path) -> dict[str, Any]:
    out = Path(output_dir)
    status = load_confirmation_status(out)
    draft = _read_json_optional(out / "sop_wi_draft.json") or {}
    payload = {
        "document_type": "sop_wi_signed_status_package",
        "job_id": status.get("job_id") or out.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": status.get("overall_status"),
        "can_release_to_shopfloor": False,
        "can_enter_release_workflow": bool(status.get("can_enter_release_workflow")),
        "release_condition": "Requires company approval before shopfloor release.",
        "confirmation_status": status,
        "draft_summary": {
            "title": draft.get("title", "连接器装配作业指导草稿"),
            "status": draft.get("status"),
            "model_origin": draft.get("model_origin"),
        },
        "warnings": _warnings(status),
    }
    (out / SIGNED_FILES["signed_json"]).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / SIGNED_FILES["signed_html"]).write_text(_render_html(payload), encoding="utf-8")
    (out / SIGNED_FILES["signed_summary_md"]).write_text(_render_md(payload), encoding="utf-8")
    _update_params(out / "params.json", status)
    return {"ok": True, "status": status.get("overall_status"), "files": dict(SIGNED_FILES), "paths": {k: out / v for k, v in SIGNED_FILES.items()}}


def _warnings(status: dict[str, Any]) -> list[str]:
    if status.get("overall_status") == "ready_for_internal_release":
        return ["已完成内部确认项，可进入企业下发审批流程；仍需按公司流程批准后下发。"]
    return ["仍有必填确认项未完成或存在驳回项，不允许下发车间。"]


def _render_html(payload: dict[str, Any]) -> str:
    status = payload["confirmation_status"]
    ready = status.get("overall_status") == "ready_for_internal_release"
    banner_class = "ready" if ready else "blocked"
    rows = "\n".join(
        "<tr>"
        f"<td>{_e(item.get('category'))}</td>"
        f"<td>{_e(item.get('label'))}</td>"
        f"<td>{_e(item.get('required'))}</td>"
        f"<td>{_e(item.get('risk_level'))}</td>"
        f"<td>{_e(item.get('status'))}</td>"
        f"<td>{_e(item.get('confirmed_by'))}</td>"
        f"<td>{_e(item.get('role'))}</td>"
        f"<td>{_e(item.get('confirmed_at'))}</td>"
        f"<td>{_e(item.get('note'))}</td>"
        "</tr>"
        for item in status.get("items", [])
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>SOP/WI 签核状态</title>
  <style>
    @page {{ size: A4; margin: 14mm; }}
    body {{ font-family: Arial, 'Microsoft YaHei', sans-serif; color: #111827; line-height: 1.45; }}
    h1 {{ margin: 0 0 6px; font-size: 24px; }}
    h2 {{ margin: 18px 0 8px; font-size: 16px; border-bottom: 1px solid #d1d5db; padding-bottom: 4px; }}
    .banner {{ padding: 11px 12px; margin: 12px 0; font-weight: 800; border: 2px solid; }}
    .blocked {{ background: #fef2f2; color: #991b1b; border-color: #dc2626; }}
    .ready {{ background: #fffbeb; color: #92400e; border-color: #f59e0b; }}
    table {{ width: 100%; border-collapse: collapse; margin: 8px 0 16px; font-size: 11px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 6px 7px; vertical-align: top; }}
    th {{ background: #f3f4f6; text-align: left; }}
    .signoff td {{ height: 42px; }}
  </style>
</head>
<body>
  <h1>SOP/WI 工程确认状态</h1>
  <div>overall_status: <strong>{_e(status.get('overall_status'))}</strong></div>
  <div>fields: confirmed_by / role / note / confirmed_at</div>
  <div>can_enter_release_workflow: <strong>{_e(status.get('can_enter_release_workflow'))}</strong></div>
  <div>can_release_to_shopfloor: <strong>false</strong></div>
  <div class="banner {banner_class}">{_e(payload['warnings'][0])}</div>
  <h2>工程确认状态</h2>
  <table>
    <thead><tr><th>类别</th><th>确认项</th><th>必填</th><th>风险</th><th>状态</th><th>确认人</th><th>角色</th><th>时间</th><th>备注</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <h2>签核栏</h2>
  <table class="signoff">
    <tr><th>工程确认</th><th>工艺确认</th><th>品质确认</th><th>批准</th></tr>
    <tr><td></td><td></td><td></td><td></td></tr>
    <tr><th>日期</th><th>日期</th><th>日期</th><th>日期</th></tr>
    <tr><td></td><td></td><td></td><td></td></tr>
  </table>
  <p>禁止声明：本文件记录人工确认状态；AI/图片生成内容仍需企业流程确认，不代表自动可生产。</p>
</body>
</html>
"""


def _render_md(payload: dict[str, Any]) -> str:
    status = payload["confirmation_status"]
    lines = [
        "# SOP/WI 签核状态摘要",
        "",
        f"- overall_status: `{status.get('overall_status')}`",
        f"- can_enter_release_workflow: `{status.get('can_enter_release_workflow')}`",
        "- can_release_to_shopfloor: `false`",
        f"- warning: {payload['warnings'][0]}",
        "",
        "## 工程确认状态",
    ]
    for item in status.get("items", []):
        lines.append(f"- {item.get('id')}: {item.get('status')} / {item.get('confirmed_by')} / {item.get('role')} / {item.get('note')}")
    return "\n".join(lines) + "\n"


def _update_params(path: Path, confirmation_status: dict[str, Any]) -> None:
    if not path.exists():
        return
    params = json.loads(path.read_text(encoding="utf-8"))
    sop_wi = params.get("sop_wi") or {}
    files = sop_wi.get("files") or {}
    files.update(SIGNED_FILES)
    sop_wi["files"] = files
    sop_wi["confirmation_status"] = {
        "overall_status": confirmation_status.get("overall_status"),
        "summary": confirmation_status.get("summary"),
        "can_release_to_shopfloor": False,
        "can_enter_release_workflow": bool(confirmation_status.get("can_enter_release_workflow")),
    }
    params["sop_wi"] = sop_wi
    path.write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json_optional(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)
