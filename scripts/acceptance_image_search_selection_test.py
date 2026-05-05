#!/usr/bin/env python3
"""Acceptance test for mock image search -> selected image -> visual CAD."""

from __future__ import annotations

import sys
import os
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
REF_IMAGE = ROOT / "backend" / "test_assets" / "connector_reference_1_968970_1.png"
BASE = os.getenv("CONNECTOR_CAD_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def head_ok(client: httpx.Client, url: str) -> bool:
    return client.head(url).status_code == 200


def main() -> int:
    if not REF_IMAGE.exists():
        print(f"Missing local test asset: {REF_IMAGE}")
        return 2

    with httpx.Client(timeout=300.0, follow_redirects=True) as client:
        asset = client.get(f"{BASE}/api/test-assets/{REF_IMAGE.name}")
        asset.raise_for_status()

        search = client.post(
            f"{BASE}/api/connector-cad/image-search",
            json={"query": "TE Connectivity 2 pin connector", "provider": "mock", "max_results": 3},
        )
        search.raise_for_status()
        search_data = search.json()
        results = search_data.get("results") or []
        if not search_data.get("search_id") or not results:
            print("Search response missing search_id or results:", search_data)
            return 1

        fetched = client.get(f"{BASE}/api/connector-cad/image-search/{search_data['search_id']}")
        fetched.raise_for_status()

        job_response = client.post(
            f"{BASE}/api/connector-cad/jobs/from-selected-image",
            json={"search_id": search_data["search_id"], "candidate_id": results[0]["id"]},
        )
        job_response.raise_for_status()
        job = job_response.json()

        job_id = job.get("job_id")
        files = job.get("files") or {}
        params_url = f"{BASE}{files.get('params_json')}"
        params = client.get(params_url).json()

        required = [
            "model_step",
            "model_stl",
            "drawing_dxf",
            "params_json",
            "image_search_results",
            "selected_image",
            "visual_recipe",
        ]
        downloadable = all(head_ok(client, f"{BASE}{files[name]}") for name in required)

    print("=== acceptance_image_search_selection_test ===")
    print("job_id:", job_id)
    print("search_id:", search_data.get("search_id"))
    print("model_origin:", params.get("model_origin"))
    print("image_search:", bool(params.get("image_search")))
    print("downloadable:", downloadable)

    ok = params.get("model_origin") == "image_search_approximated" and bool(params.get("image_search")) and downloadable
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
