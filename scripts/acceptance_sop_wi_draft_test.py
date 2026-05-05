"""Acceptance: SOP/WI draft package is generated for image-derived flat CAD jobs."""

from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8000"
QUERY = "1-968970-1 connector"


def request(url: str, data: bytes | None = None, method: str = "GET", timeout: float = 120) -> bytes:
    headers = {"Content-Type": "application/json"} if data else {}
    req = Request(url, data=data, method=method, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_json(url: str, data: bytes | None = None, method: str = "GET", timeout: float = 120) -> dict:
    return json.loads(request(url, data=data, method=method, timeout=timeout).decode("utf-8"))


def wait_job(job_id: str, attempts: int = 60) -> dict:
    last = {}
    for _ in range(attempts):
        last = get_json(f"{BASE}/api/connector-cad/jobs/{job_id}", timeout=240)
        if last.get("status") in ("completed", "needs_confirmation", "failed"):
            return last
        time.sleep(1.2)
    return last


def head_ok(job_id: str, filename: str) -> bool:
    try:
        req = Request(f"{BASE}/api/connector-cad/jobs/{job_id}/files/{filename}", method="HEAD")
        with urlopen(req, timeout=120) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def main() -> int:
    print("Checking backend...")
    try:
        get_json(f"{BASE}/api/ai/status")
    except (HTTPError, URLError) as exc:
        print("FAIL backend:", exc)
        return 2

    print("Creating job:", QUERY)
    body = json.dumps({"input_type": "text", "text": QUERY}).encode("utf-8")
    try:
        created = get_json(f"{BASE}/api/connector-cad/jobs", data=body, method="POST", timeout=600)
    except HTTPError as exc:
        print("FAIL create:", exc.read().decode("utf-8", errors="replace"))
        return 3
    job_id = created.get("job_id")
    final = wait_job(job_id)
    params = final.get("params") or {}
    flat_cad = params.get("flat_cad") or {}
    sop_wi = params.get("sop_wi") or {}
    print("job_id:", job_id)
    print("model_origin:", params.get("model_origin"))
    print("flat_cad.enabled:", flat_cad.get("enabled"))
    print("sop_wi.enabled:", sop_wi.get("enabled"))
    print("sop_wi.status:", sop_wi.get("status"))

    if flat_cad.get("enabled") is not True:
        print("FAIL flat_cad.enabled is not true")
        return 4
    if sop_wi.get("enabled") is not True:
        print("FAIL sop_wi.enabled is not true")
        return 5

    required = [
        "sop_wi_draft.json",
        "sop_wi_draft.html",
        "sop_wi_summary.md",
        "engineering_confirmation_checklist.json",
        "sop_wi_assets_manifest.json",
    ]
    missing = [filename for filename in required if not head_ok(job_id, filename)]
    if missing:
        print("FAIL missing SOP/WI downloads:", missing)
        return 6

    checklist = get_json(f"{BASE}/api/connector-cad/jobs/{job_id}/files/engineering_confirmation_checklist.json")
    checklist_summary = checklist.get("summary") or {}
    draft = get_json(f"{BASE}/api/connector-cad/jobs/{job_id}/files/sop_wi_draft.json")
    html_text = request(f"{BASE}/api/connector-cad/jobs/{job_id}/files/sop_wi_draft.html").decode("utf-8", errors="replace")
    md_text = request(f"{BASE}/api/connector-cad/jobs/{job_id}/files/sop_wi_summary.md").decode("utf-8", errors="replace")

    print("required_count:", checklist_summary.get("required_count"))
    print("pending_count:", checklist_summary.get("pending_count"))
    print("high_risk_count:", checklist_summary.get("high_risk_count"))
    print("can_release_to_shopfloor:", checklist_summary.get("can_release_to_shopfloor"))

    if int(checklist_summary.get("required_count") or 0) <= 0:
        print("FAIL empty required checklist")
        return 7
    if int(checklist_summary.get("pending_count") or 0) <= 0:
        print("FAIL no pending checklist items")
        return 8
    if checklist_summary.get("can_release_to_shopfloor") is not False:
        print("FAIL checklist allows shopfloor release")
        return 9
    for text in ["连接器装配作业指导草稿", "端子插入方向", "工程确认清单", "非原厂制造尺寸图"]:
        if text not in html_text:
            print("FAIL HTML missing:", text)
            return 10
    forbidden = ["可直接生产", "可直接投产"]
    if any(term in html_text or term in md_text or term in json.dumps(draft, ensure_ascii=False) for term in forbidden):
        print("FAIL forbidden production claim found")
        return 11

    if head_ok(job_id, "sop_wi_draft.pdf"):
        print("PDF: available")
    else:
        print("PDF: not generated (warning only)")

    print("PASS SOP/WI draft job_id=", job_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
