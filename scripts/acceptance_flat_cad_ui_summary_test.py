"""Acceptance: flat CAD UI summary data is present for frontend rendering.

Run with backend on http://127.0.0.1:8000.
This script intentionally avoids browser automation; it verifies that the job
payload and downloadable reports contain the fields used by the result page.
"""

from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8000"
QUERY = "1-968970-1 connector"

EXPECTED_FILE_KEYS = {
    "front_view_dxf": "connector_front_view.dxf",
    "rear_view_dxf": "connector_rear_view.dxf",
    "top_view_dxf": "connector_top_view.dxf",
    "side_view_dxf": "connector_side_view.dxf",
    "insertion_direction_dxf": "connector_insertion_direction.dxf",
    "flat_views_svg": "connector_flat_views.svg",
    "recipe": "connector_2d_recipe.json",
    "view_classification": "connector_view_classification.json",
    "terminal_insertion": "terminal_insertion.json",
    "structure_report": "structure_completeness_report.json",
}


def request(url: str, data: bytes | None = None, method: str = "GET", timeout: float = 120) -> bytes:
    headers = {"Content-Type": "application/json"} if data else {}
    req = Request(url, data=data, method=method, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_json(url: str, data: bytes | None = None, method: str = "GET", timeout: float = 120) -> dict:
    return json.loads(request(url, data=data, method=method, timeout=timeout).decode("utf-8"))


def wait_job(job_id: str, attempts: int = 40) -> dict:
    last: dict = {}
    for _ in range(attempts):
        last = get_json(f"{BASE}/api/connector-cad/jobs/{job_id}")
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


def derive_sop_ready(structure_status: str, terminal_exists: bool) -> str:
    if structure_status == "insufficient":
        return "no"
    if structure_status == "complete" and terminal_exists:
        return "caution"
    return "caution"


def main() -> int:
    print("Checking backend...")
    try:
        get_json(f"{BASE}/api/ai/status")
    except (URLError, HTTPError) as exc:
        print("FAIL: backend not reachable:", exc)
        return 2

    print("Creating flat CAD UI summary job:", QUERY)
    body = json.dumps({"input_type": "text", "text": QUERY}).encode("utf-8")
    try:
        created = get_json(f"{BASE}/api/connector-cad/jobs", data=body, method="POST", timeout=600)
    except HTTPError as exc:
        print("FAIL: job create failed:", exc.read().decode("utf-8", errors="replace"))
        return 3

    job_id = created.get("job_id")
    if not job_id:
        print("FAIL: no job_id:", created)
        return 3

    final = wait_job(job_id)
    if final.get("status") not in ("completed", "needs_confirmation"):
        print("FAIL: job did not reach a usable result:", final.get("status"), final.get("error"))
        return 4

    params = final.get("params") or {}
    flat_cad = params.get("flat_cad") or {}
    files = flat_cad.get("files") or {}
    structure = flat_cad.get("structure_completeness") or {}

    print("job_id:", job_id)
    print("model_origin:", params.get("model_origin"))
    print("flat_cad.enabled:", flat_cad.get("enabled"))
    print("flat_cad.status:", flat_cad.get("status"))
    print("structure status:", structure.get("status"), "score:", structure.get("score"))

    if flat_cad.get("enabled") is not True:
        print("FAIL: flat_cad.enabled is not true")
        return 5
    if flat_cad.get("status") == "failed":
        print("FAIL: flat_cad.status failed")
        return 6

    missing_keys = [key for key, filename in EXPECTED_FILE_KEYS.items() if files.get(key) != filename]
    if missing_keys:
        print("FAIL: flat_cad.files missing or mismatched:", missing_keys)
        return 7

    missing_downloads = [filename for filename in EXPECTED_FILE_KEYS.values() if not head_ok(job_id, filename)]
    if missing_downloads:
        print("FAIL: flat CAD UI downloads missing:", missing_downloads)
        return 8

    terminal = get_json(f"{BASE}/api/connector-cad/jobs/{job_id}/files/terminal_insertion.json")
    structure_report = get_json(f"{BASE}/api/connector-cad/jobs/{job_id}/files/structure_completeness_report.json")
    svg = request(f"{BASE}/api/connector-cad/jobs/{job_id}/files/connector_flat_views.svg")

    terminal_data = terminal.get("terminal_insertion") or {}
    report_data = structure_report.get("structure_completeness") or structure_report
    sop_ready = derive_sop_ready(str(report_data.get("status") or ""), bool(terminal_data))

    print("recommended_insertion_face:", terminal_data.get("recommended_insertion_face"))
    print("opposite_mating_face:", terminal_data.get("opposite_mating_face"))
    print("insertion_direction:", terminal_data.get("insertion_direction"))
    print("view_for_work_instruction:", terminal_data.get("view_for_work_instruction"))
    print("view_for_pin_check:", terminal_data.get("view_for_pin_check"))
    print("terminal confidence:", terminal_data.get("confidence"))
    print("requires_manual_confirmation:", terminal_data.get("requires_manual_confirmation"))
    print("report checks:", sorted((report_data.get("checks") or {}).keys()))
    print("report missing_items:", report_data.get("missing_items") or [])
    print("report warnings:", report_data.get("warnings") or [])
    print("svg bytes:", len(svg))
    print("derived sop_ready:", sop_ready)

    if not terminal_data.get("recommended_insertion_face"):
        print("FAIL: terminal insertion summary lacks recommended_insertion_face")
        return 9
    if "checks" not in report_data:
        print("FAIL: structure report lacks checks")
        return 10
    if b"<svg" not in svg[:500].lower():
        print("FAIL: connector_flat_views.svg is not SVG-like")
        return 11

    print("PASS flat CAD UI summary job_id=", job_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
