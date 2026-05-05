from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import quote

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8000"


def _post_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = Request(f"{API}{path}", data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"POST {path} failed: HTTP {exc.code} {detail}") from exc


def _get_json(path: str) -> dict:
    with urlopen(f"{API}{path}", timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_json(job: dict, key: str) -> dict:
    url = job.get("files", {}).get(key)
    if not url:
        raise AssertionError(f"Missing download URL for {key}")
    return _get_json(url)


def _poll(job_id: str) -> dict:
    last = None
    for _ in range(90):
        last = _get_json(f"/api/connector-cad/jobs/{job_id}")
        if last.get("status") in {"completed", "needs_confirmation", "failed"}:
            return last
        time.sleep(1.0)
    raise AssertionError(f"Job {job_id} did not finish; last={last}")


def _file_url(path: Path) -> str:
    return "file:///" + quote(str(path.resolve()).replace("\\", "/"), safe="/:")


def _manual_job(query: str, image_url: str, title: str) -> dict:
    created = _post_json(
        "/api/connector-cad/jobs/from-manual-image-url",
        {"query": query, "image_url": image_url, "source_url": image_url, "title": title},
    )
    return _poll(created["job_id"])


def _make_black_cylinder(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (420, 280), "white")
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((80, 105, 285, 175), radius=34, fill=(18, 18, 20), outline=(5, 5, 6), width=5)
    draw.ellipse((245, 82, 365, 202), fill=(12, 12, 14), outline=(0, 0, 0), width=6)
    draw.ellipse((288, 124, 322, 158), fill=(240, 240, 240), outline=(40, 40, 40), width=3)
    draw.rectangle((45, 124, 90, 156), fill=(30, 30, 34), outline=(5, 5, 8), width=3)
    draw.rectangle((120, 92, 220, 104), fill=(30, 30, 34))
    img.save(path)


def _assert_consistency_ok(params: dict) -> dict:
    consistency = params.get("generation_consistency") or {}
    if consistency.get("recipe_color_matches_image") is not True:
        raise AssertionError(f"Color consistency failed: {json.dumps(consistency, ensure_ascii=False)}")
    if consistency.get("recipe_shape_matches_image") is not True:
        raise AssertionError(f"Shape consistency failed: {json.dumps(consistency, ensure_ascii=False)}")
    return consistency


def test_blue_reference() -> dict:
    image_url = f"{API}/api/test-assets/connector_reference_1_968970_1.png"
    job = _manual_job("1-968970-1 connector blue reference", image_url, "local blue connector reference")
    if job.get("status") == "failed":
        raise AssertionError(f"Blue reference job failed: {job.get('error')}")
    params = job["params"]
    features = _download_json(job, "image_features")
    recipe = _download_json(job, "visual_recipe")
    consistency = _assert_consistency_ok(params)
    if features.get("dominant_color") != "blue":
        raise AssertionError(f"Expected blue dominant color, got {features.get('dominant_color')}")
    if recipe.get("color") != "blue":
        raise AssertionError(f"Expected blue recipe color, got {recipe.get('color')}")
    if recipe.get("base_body", {}).get("type") == "cylindrical_connector":
        raise AssertionError("Blue rectangular reference was classified as cylindrical")
    return {"job_id": job["job_id"], "consistency": consistency}


def test_black_cylinder() -> dict:
    tmp = ROOT / "backend" / "outputs" / "_acceptance_tmp" / "synthetic_black_cylindrical_connector.png"
    _make_black_cylinder(tmp)
    job = _manual_job("synthetic black cylindrical connector", _file_url(tmp), "synthetic black cylindrical connector")
    if job.get("status") == "failed":
        raise AssertionError(f"Black cylinder job failed: {job.get('error')}")
    params = job["params"]
    features = _download_json(job, "image_features")
    recipe = _download_json(job, "visual_recipe")
    consistency = _assert_consistency_ok(params)
    body_type = recipe.get("base_body", {}).get("type")
    if features.get("dominant_color") != "black":
        raise AssertionError(f"Expected black/dark dominant color, got {features.get('dominant_color')}")
    if recipe.get("color") == "blue":
        raise AssertionError("Black cylinder recipe incorrectly used blue")
    if body_type != "cylindrical_connector":
        raise AssertionError(f"Expected cylindrical_connector body type, got {body_type}")
    if params.get("template_name") == "TE_BLUE_MULTI_CAVITY":
        raise AssertionError("Black cylinder used old TE blue template")
    return {"job_id": job["job_id"], "consistency": consistency}


def test_non_image_rejected() -> dict:
    tmp = ROOT / "backend" / "outputs" / "_acceptance_tmp" / "fake_image.png"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text("<html><body>not an image</body></html>", encoding="utf-8")
    job = _manual_job("html masquerading as image", _file_url(tmp), "html non image")
    if job.get("status") != "failed":
        raise AssertionError(f"Expected non-image job to fail, got {job.get('status')}")
    text = json.dumps(job.get("params", {}), ensure_ascii=False).lower()
    if "fallback_blocked" not in text and "not an image" not in text and "decode" not in text:
        raise AssertionError("Non-image failure did not report decode/download problem")
    return {"job_id": job["job_id"], "status": job.get("status"), "error": job.get("error")}


def main() -> int:
    try:
        status = _get_json("/api/ai/status")
        print(
            "AI status:",
            {
                "configured": status.get("configured"),
                "base_url_set": status.get("base_url_set"),
                "api_key_set": status.get("api_key_set"),
                "provider": status.get("provider"),
                "model": status.get("model"),
                "error_type": status.get("error_type"),
            },
        )
        blue = test_blue_reference()
        print("BLUE_REFERENCE_OK", json.dumps(blue, ensure_ascii=False))
        black = test_black_cylinder()
        print("BLACK_CYLINDER_OK", json.dumps(black, ensure_ascii=False))
        non_image = test_non_image_rejected()
        print("NON_IMAGE_REJECTED_OK", json.dumps(non_image, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
