"""Acceptance: editable engineering confirmation status and signed SOP/WI export."""

from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8000"
QUERY = "1-968970-1 connector"


def request(url: str, data: bytes | None = None, method: str = "GET", timeout: float = 180) -> bytes:
    headers = {"Content-Type": "application/json"} if data else {}
    req = Request(url, data=data, method=method, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_json(url: str, data: bytes | None = None, method: str = "GET", timeout: float = 180) -> dict:
    return json.loads(request(url, data=data, method=method, timeout=timeout).decode("utf-8"))


def wait_job(job_id: str, attempts: int = 60) -> dict:
    last = {}
    for _ in range(attempts):
        last = get_json(f"{BASE}/api/connector-cad/jobs/{job_id}", timeout=240)
        if last.get("status") in ("completed", "needs_confirmation", "failed"):
            return last
        time.sleep(1.2)
    return last


def patch_item(job_id: str, item_id: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    return get_json(f"{BASE}/api/connector-cad/jobs/{job_id}/confirmation-status/items/{item_id}", data=body, method="PATCH")


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
    created = get_json(f"{BASE}/api/connector-cad/jobs", data=body, method="POST", timeout=600)
    job_id = created.get("job_id")
    final = wait_job(job_id)
    params = final.get("params") or {}
    if (params.get("sop_wi") or {}).get("enabled") is not True:
        print("FAIL sop_wi.enabled is not true")
        return 3

    status = get_json(f"{BASE}/api/connector-cad/jobs/{job_id}/confirmation-status")
    summary = status.get("summary") or {}
    print("job_id:", job_id)
    print("initial overall_status:", status.get("overall_status"))
    print("required_count:", summary.get("required_count"))
    if int(summary.get("required_count") or 0) <= 0:
        print("FAIL no required confirmation items")
        return 4

    required_items = [item for item in status.get("items", []) if item.get("required")]
    first = required_items[0]
    updated = patch_item(
        job_id,
        first["id"],
        {"status": "confirmed", "note": "已按实物确认", "confirmed_by": "验收工程", "role": "engineering"},
    )
    first_after = next(item for item in updated["items"] if item["id"] == first["id"])
    if not first_after.get("history") or first_after.get("status") != "confirmed":
        print("FAIL history/status not written for confirmed item")
        return 5

    second = required_items[1] if len(required_items) > 1 else first
    rejected = patch_item(
        job_id,
        second["id"],
        {"status": "rejected", "note": "验收测试驳回", "confirmed_by": "验收品质", "role": "quality"},
    )
    if rejected.get("overall_status") != "rejected":
        print("FAIL rejected item did not set overall_status=rejected")
        return 6

    reset = get_json(f"{BASE}/api/connector-cad/jobs/{job_id}/confirmation-status/reset", data=b"{}", method="POST")
    if reset.get("overall_status") != "pending":
        print("FAIL reset did not restore pending")
        return 7

    for idx, item in enumerate([item for item in reset.get("items", []) if item.get("required")], start=1):
        patch_item(
            job_id,
            item["id"],
            {
                "status": "confirmed",
                "note": f"验收确认 {idx}",
                "confirmed_by": f"验收人员{idx}",
                "role": ["engineering", "process", "quality"][idx % 3],
            },
        )
    ready = get_json(f"{BASE}/api/connector-cad/jobs/{job_id}/confirmation-status")
    print("ready overall_status:", ready.get("overall_status"))
    print("can_enter_release_workflow:", ready.get("can_enter_release_workflow"))
    if ready.get("overall_status") != "ready_for_internal_release" and ready.get("can_enter_release_workflow") is not True:
        print("FAIL all required confirmed did not enable release workflow")
        return 8

    exported = get_json(f"{BASE}/api/connector-cad/jobs/{job_id}/sop-wi/export-signed", data=b"{}", method="POST")
    print("signed export status:", exported.get("status"))
    required_files = [
        "confirmation_status.json",
        "sop_wi_signed.html",
        "sop_wi_signed.json",
        "sop_wi_signed_summary.md",
    ]
    missing = [filename for filename in required_files if not head_ok(job_id, filename)]
    if missing:
        print("FAIL signed files missing:", missing)
        return 9

    signed_html = request(f"{BASE}/api/connector-cad/jobs/{job_id}/files/sop_wi_signed.html").decode("utf-8", errors="replace")
    for text in ["工程确认状态", "confirmed_by", "role"]:
        if text not in signed_html:
            print("FAIL signed HTML missing:", text)
            return 10
    if "不允许下发车间" not in signed_html and "可进入企业下发审批流程" not in signed_html:
        print("FAIL signed HTML missing release warning")
        return 11
    if "AI 已确认可直接生产" in signed_html:
        print("FAIL forbidden production claim found")
        return 12

    print("PASS confirmation status job_id=", job_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
