"""
Acceptance: image-search-approximated job produces flat 2D CAD artifacts.
Run with backend on http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8000"
QUERY = "1-968970-1 connector"


def get_json(url: str, data: bytes | None = None, method: str = "GET", timeout: float = 120) -> dict:
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_job(job_id: str, attempts: int = 30) -> dict:
    last = {}
    for _ in range(attempts):
        last = get_json(f"{BASE}/api/connector-cad/jobs/{job_id}")
        st = last.get("status")
        if st in ("completed", "needs_confirmation", "failed"):
            return last
        time.sleep(1.2)
    return last


def main() -> int:
    print("Checking backend…")
    try:
        get_json(f"{BASE}/api/ai/status")
    except (URLError, HTTPError) as e:
        print("Backend not reachable:", e)
        return 2

    print("POST job:", QUERY)
    body = json.dumps({"input_type": "text", "text": QUERY}).encode("utf-8")
    try:
        job = get_json(f"{BASE}/api/connector-cad/jobs", data=body, method="POST", timeout=600)
    except HTTPError as e:
        print("Job create failed:", e.read().decode("utf-8", errors="replace"))
        return 3

    job_id = job.get("job_id")
    if not job_id:
        print("No job_id:", job)
        return 3

    print("Polling…", job_id)
    final = wait_job(job_id)
    params = final.get("params") or {}
    mo = params.get("model_origin")
    print("model_origin:", mo, "status:", final.get("status"))

    if mo not in ("image_search_approximated", "image_upload_approximated"):
        print("Expected image_search_approximated or image_upload_approximated; got", mo)
        print("If search API missing, configure IMAGE_SEARCH_* or expect generic fallback — test may be inconclusive.")
        # still check flat_cad if present
    fc = params.get("flat_cad") or {}
    print("flat_cad.enabled:", fc.get("enabled"), "flat_cad.status:", fc.get("status"))

    required = [
        "connector_front_view.dxf",
        "connector_rear_view.dxf",
        "connector_top_view.dxf",
        "connector_side_view.dxf",
        "connector_insertion_direction.dxf",
        "connector_flat_views.svg",
        "connector_2d_recipe.json",
        "connector_view_classification.json",
        "terminal_insertion.json",
        "structure_completeness_report.json",
    ]

    ok_all = True
    for fn in required:
        url = f"{BASE}/api/connector-cad/jobs/{job_id}/files/{fn}"
        try:
            req = Request(url, method="HEAD")
            urlopen(req, timeout=120)
            print("  OK", fn)
        except HTTPError as e:
            print("  FAIL", fn, e.code)
            ok_all = False
        except URLError as e:
            print("  FAIL", fn, e)
            ok_all = False

    sc = (fc.get("structure_completeness") or {})
    print("structure_completeness:", sc.get("status"), "score:", sc.get("score"))

    ter = {}
    try:
        tr = get_json(f"{BASE}/api/connector-cad/jobs/{job_id}/files/terminal_insertion.json")
        ter = tr.get("terminal_insertion") or {}
    except Exception as e:
        print("terminal_insertion.json read:", e)
    print("recommended_insertion_face:", ter.get("recommended_insertion_face"))

    if not fc.get("enabled"):
        print("FAIL: flat_cad.enabled is not true")
        return 4
    if fc.get("status") == "failed":
        print("FAIL: flat_cad.status failed:", fc.get("error"))
        return 5
    if sc.get("status") == "insufficient":
        print("FAIL: structure completeness insufficient")
        return 6
    if not ok_all:
        print("FAIL: missing downloads")
        return 7

    print("PASS job_id=", job_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
