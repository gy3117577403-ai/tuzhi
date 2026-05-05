#!/usr/bin/env python3
"""Acceptance tests for image search selection and manual URL visual CAD."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
REF_IMAGE = BACKEND / "test_assets" / "connector_reference_1_968970_1.png"
BASE = os.getenv("CONNECTOR_CAD_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def _provider_is_mock() -> bool:
    env_path = BACKEND / ".env"
    if not env_path.exists():
        return False
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip().lower() == "image_search_provider=mock":
            return True
    return False


def head_ok(client: httpx.Client, url: str) -> bool:
    response = client.head(url)
    return response.status_code == 200


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_downloads(client: httpx.Client, files: dict, keys: list[str]) -> bool:
    return all(files.get(key) and head_ok(client, f"{BASE}{files[key]}") for key in keys)


def print_candidate_quality(results: list[dict]) -> None:
    exact_exists = False
    top_level = ""
    for index, candidate in enumerate(results, 1):
        part_match = candidate.get("part_match") or {}
        level = part_match.get("match_level")
        matched = part_match.get("matched_part_number") or ""
        rank_reason = candidate.get("rank_reason") or ""
        if index == 1:
            top_level = level or ""
        if level == "exact":
            exact_exists = True
        require(bool(part_match), f"candidate {index} missing part_match")
        require(bool(level), f"candidate {index} missing part_match.match_level")
        if level == "near_miss":
            require(bool(part_match.get("reason")), f"near_miss candidate {index} missing reason")
            print(f"WARNING: candidate {index} is near_miss for {matched or 'unknown part'}")
        print(f"candidate_{index}_title:", candidate.get("title") or "")
        print(f"candidate_{index}_domain:", candidate.get("domain") or "")
        print(f"candidate_{index}_score:", candidate.get("score"))
        print(f"candidate_{index}_match_level:", level)
        print(f"candidate_{index}_matched_part_number:", matched)
        print(f"candidate_{index}_rank_reason:", rank_reason)
    if top_level == "near_miss":
        print("WARNING: top candidate is near_miss; user review is required.")
    if exact_exists and top_level != "exact":
        print("WARNING: exact candidate exists but top candidate is not exact.")


def run_mock_selection(client: httpx.Client) -> dict:
    print("=== A. mock provider selection ===")
    print("env_provider_mock:", _provider_is_mock())
    asset = client.get(f"{BASE}/api/test-assets/{REF_IMAGE.name}")
    asset.raise_for_status()

    search = client.post(
        f"{BASE}/api/connector-cad/image-search",
        json={"query": "1-968970-1 connector", "provider": "mock", "max_results": 8},
    )
    search.raise_for_status()
    search_data = search.json()
    results = search_data.get("results") or []
    require(search_data.get("status") == "success", f"mock search status was {search_data.get('status')}")
    require(len(results) >= 1, "mock search returned no candidates")
    require(results[0].get("score") is not None, "candidate missing score")
    require(bool(results[0].get("rank_reason")), "candidate missing rank_reason")
    print_candidate_quality(results)

    fetched = client.get(f"{BASE}/api/connector-cad/image-search/{search_data['search_id']}")
    fetched.raise_for_status()

    job_response = client.post(
        f"{BASE}/api/connector-cad/jobs/from-selected-image",
        json={"search_id": search_data["search_id"], "candidate_id": results[0]["id"]},
    )
    job_response.raise_for_status()
    job = job_response.json()
    files = job.get("files") or {}
    params = client.get(f"{BASE}{files.get('params_json')}").json()
    required = [
        "model_step",
        "model_stl",
        "drawing_dxf",
        "params_json",
        "source_manifest",
        "image_search_results",
        "selected_image",
        "image_features",
        "vision_report",
        "visual_recipe",
    ]
    downloadable = check_downloads(client, files, required)
    require(params.get("model_origin") == "image_search_approximated", "selected-image job did not use image_search_approximated")
    require(downloadable, "not all selected-image files are downloadable")

    print("search_status:", search_data.get("status"))
    print("provider:", search_data.get("provider"))
    print("candidates:", len(results))
    print("top_score:", results[0].get("score"))
    print("top_match_level:", (results[0].get("part_match") or {}).get("match_level"))
    print("top_rank_reason:", results[0].get("rank_reason"))
    print("job_id:", job.get("job_id"))
    print("model_origin:", params.get("model_origin"))
    print("downloadable:", downloadable)
    return {"search": search_data, "job": job, "params": params}


def run_current_provider_part_risk(client: httpx.Client) -> dict:
    print("=== A2. current provider part-match risk ===")
    response = client.post(
        f"{BASE}/api/connector-cad/image-search",
        json={"query": "1-968970-1 connector", "max_results": 8},
    )
    response.raise_for_status()
    search_data = response.json()
    results = search_data.get("results") or []
    require(search_data.get("status") in {"success", "not_configured", "failed"}, "unexpected search status")
    print("provider:", search_data.get("provider"))
    print("status:", search_data.get("status"))
    print("match_summary:", search_data.get("match_summary"))
    print("refined_searches:", len(search_data.get("refined_searches") or []))
    if search_data.get("status") != "success" or not results:
        print("current provider did not return candidates; skipping risk gate generation check")
        return {"search": search_data, "job": None, "params": {}}

    print_candidate_quality(results)
    exact = next((item for item in results if (item.get("part_match") or {}).get("match_level") == "exact"), None)
    near_candidate = next((item for item in results if (item.get("part_match") or {}).get("match_level") == "near_miss"), None)
    selected = exact or results[0]
    selected_level = (selected.get("part_match") or {}).get("match_level")
    print("selected_match_level:", selected_level)

    if near_candidate:
        blocked = client.post(
            f"{BASE}/api/connector-cad/jobs/from-selected-image",
            json={"search_id": search_data["search_id"], "candidate_id": near_candidate["id"], "query": "1-968970-1 connector"},
        )
        require(blocked.status_code in {400, 409}, f"near_miss was not blocked, status={blocked.status_code}")
        blocked_data = blocked.json()
        detail = blocked_data.get("detail") or {}
        require(detail.get("status") == "requires_confirmation", "near_miss block did not require confirmation")
        print("near_miss_blocked:", True)

    job_response = client.post(
        f"{BASE}/api/connector-cad/jobs/from-selected-image",
        json={
            "search_id": search_data["search_id"],
            "candidate_id": selected["id"],
            "query": "1-968970-1 connector",
            "accept_part_mismatch_risk": selected_level == "near_miss",
        },
    )
    job_response.raise_for_status()
    job = job_response.json()
    files = job.get("files") or {}
    params = client.get(f"{BASE}{files.get('params_json')}").json()
    image_search = params.get("image_search") or {}
    require(params.get("model_origin") == "image_search_approximated", "current-provider job did not use image_search_approximated")
    require(bool(image_search.get("selected_part_match")), "params.json missing image_search.selected_part_match")
    if selected_level == "near_miss":
        require(image_search.get("part_mismatch_risk_accepted") is True, "near_miss acceptance was not recorded")
    print("job_id:", job.get("job_id"))
    print("model_origin:", params.get("model_origin"))
    print("part_mismatch_risk_accepted:", image_search.get("part_mismatch_risk_accepted"))
    return {"search": search_data, "job": job, "params": params}


def run_not_configured(client: httpx.Client) -> None:
    print("=== B. not_configured compatibility ===")
    response = client.post(
        f"{BASE}/api/connector-cad/image-search",
        json={"query": "1-968970-1 connector", "provider": "manual_url", "max_results": 2},
    )
    response.raise_for_status()
    data = response.json()
    print("status:", data.get("status"))
    print("provider:", data.get("provider"))
    print("warnings:", len(data.get("warnings") or []))
    require(data.get("status") == "not_configured", "manual_url compatibility did not return not_configured")


def run_manual_url(client: httpx.Client) -> dict:
    print("=== C. manual URL visual CAD ===")
    image_url = f"{BASE}/api/test-assets/{REF_IMAGE.name}"
    payload = {
        "query": "1-968970-1 connector",
        "image_url": image_url,
        "source_url": "local-test",
        "title": "manual local test image",
    }
    response = client.post(f"{BASE}/api/connector-cad/jobs/from-manual-image-url", json=payload)
    response.raise_for_status()
    job = response.json()
    files = job.get("files") or {}
    params = client.get(f"{BASE}{files.get('params_json')}").json()
    downloadable = check_downloads(client, files, ["selected_image", "visual_recipe", "model_step", "model_stl", "drawing_dxf"])
    require(params.get("model_origin") == "image_search_approximated", "manual-url job did not use image_search_approximated")
    require((params.get("image_search") or {}).get("manual_image_url_unverified") is True, "manual URL unverified flag missing")
    require(downloadable, "not all manual-url files are downloadable")
    print("job_id:", job.get("job_id"))
    print("model_origin:", params.get("model_origin"))
    print("downloadable:", downloadable)
    return {"job": job, "params": params}


def main() -> int:
    if not REF_IMAGE.exists():
        print(f"Missing local test asset: {REF_IMAGE}")
        return 2
    try:
        with httpx.Client(timeout=300.0, follow_redirects=True) as client:
            mock = run_mock_selection(client)
            current_provider = run_current_provider_part_risk(client)
            run_not_configured(client)
            manual = run_manual_url(client)
        print("=== acceptance_image_search_selection_test PASS ===")
        print("mock_job_id:", mock["job"].get("job_id"))
        if current_provider.get("job"):
            print("current_provider_job_id:", current_provider["job"].get("job_id"))
        print("manual_job_id:", manual["job"].get("job_id"))
        return 0
    except Exception as exc:
        print("ACCEPTANCE FAILED:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
