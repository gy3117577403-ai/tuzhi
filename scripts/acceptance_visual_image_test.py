#!/usr/bin/env python3
"""Upload acceptance test: real connector photo → image_upload_approximated visual CAD."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
REF_IMAGE = ROOT / "backend" / "test_assets" / "connector_reference_1_968970_1.png"
BASE = "http://127.0.0.1:8000"


def head_ok(url: str) -> tuple[bool, int | str]:
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            r = client.head(url)
            return r.status_code == 200, r.status_code
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    if not REF_IMAGE.exists():
        print("請把真實連接器圖片保存為：")
        print(f"  {REF_IMAGE}")
        print("（不要用 picsum 或占位隨機圖代替真實連接器照片。）")
        return 2

    mime = "image/png"
    suf = REF_IMAGE.suffix.lower()
    if suf in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif suf == ".webp":
        mime = "image/webp"

    with httpx.Client(timeout=300.0) as client:
        files = {"file": (REF_IMAGE.name, REF_IMAGE.read_bytes(), mime)}
        data = {"input_type": "photo"}
        r = client.post(f"{BASE}/api/connector-cad/jobs", files=files, data=data)
        r.raise_for_status()
        job = r.json()

    job_id = job.get("job_id")
    if not job_id:
        print("No job_id in response:", job)
        return 1

    base_files = f"{BASE}/api/connector-cad/jobs/{job_id}/files"
    params_url = f"{base_files}/params.json"
    ifeat_url = f"{base_files}/image_features.json"
    vis_url = f"{base_files}/vision_report.json"
    recipe_url = f"{base_files}/visual_recipe.json"

    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        pres = client.get(params_url)
        pres.raise_for_status()
        params = pres.json()
        ires = client.get(ifeat_url)
        imgs = ires.json() if ires.status_code == 200 else {}
        vres = client.get(vis_url)
        rres = client.get(recipe_url)
        recipe = rres.json() if rres.status_code == 200 else {}

    ff = imgs.get("feature_flags") or {}
    layout = imgs.get("front_face_layout") or {}
    origin = params.get("model_origin")
    ap = params.get("appearance_pipeline") or {}
    fb = ap.get("fallback_reason")

    vr = params.get("visual_recipe") or recipe
    warns = list(imgs.get("warnings") or [])
    if isinstance(vr, dict) and vr.get("warnings"):
        warns.extend(vr["warnings"] if isinstance(vr["warnings"], list) else [str(vr["warnings"])])

    print("=== acceptance_visual_image_test ===")
    print("1. job_id:", job_id)
    print("2. model_origin:", origin)
    print("3. dominant_color:", imgs.get("dominant_color"))
    print("4. front_face_layout:", json.dumps(layout, ensure_ascii=False))
    print("5. feature_flags:", json.dumps(ff, ensure_ascii=False))
    print("6. visual_recipe (摘要鍵):", list(vr.keys()) if isinstance(vr, dict) else vr)
    if isinstance(vr, dict):
        print("   color:", vr.get("color"))
        print("   confidence:", vr.get("confidence"))

    checks = {
        "params.json": head_ok(params_url),
        "image_features.json": head_ok(ifeat_url),
        "vision_report.json": head_ok(vis_url),
        "visual_recipe.json": head_ok(recipe_url),
        "model.step": head_ok(f"{base_files}/model.step"),
        "model.stl": head_ok(f"{base_files}/model.stl"),
        "drawing.dxf": head_ok(f"{base_files}/drawing.dxf"),
    }
    print("\n7–9. 可下載檔（HTTP HEAD）:")
    for name, (ok, code) in checks.items():
        tag = name
        if name == "image_features.json":
            tag = "7. image_features.json"
        elif name == "vision_report.json":
            tag = "8. vision_report.json"
        elif name == "visual_recipe.json":
            tag = "9. visual_recipe.json"
        print(f"  {tag}: {'可下載' if ok else '失敗'} ({code})")

    if warns:
        print("\nwarnings:", json.dumps(warns, ensure_ascii=False)[:2000])

    if origin == "generic_mvp" and fb:
        print("\n⚠ generic_mvp fallback_reason:", fb)

    ok_origin = origin == "image_upload_approximated"
    keys_needed = ["front_shroud", "cavity_array", "top_features", "side_features", "color"]
    recipe_ok = isinstance(vr, dict) and all(k in vr for k in keys_needed)

    pass_approx = ok_origin and recipe_ok and checks["visual_recipe.json"][0]
    print("\n10. 通過 image_upload_approximated 驗收:", pass_approx)

    return 0 if pass_approx else 1


if __name__ == "__main__":
    sys.exit(main())
