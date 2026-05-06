from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw


BASE_URL = "http://127.0.0.1:8000"


def request_json(method: str, path: str, payload: dict | None = None) -> dict:
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"{method} {path} failed: HTTP {exc.code} {detail}") from exc
    except URLError as exc:
        raise AssertionError(f"{method} {path} failed: {exc}") from exc


def multipart_upload(path: Path) -> dict:
    boundary = "----procurement-image-keyword-boundary"
    body = b"".join(
        [
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                "Content-Type: image/png\r\n\r\n"
            ).encode("utf-8"),
            path.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    req = Request(
        f"{BASE_URL}/api/procurement/image-keywords",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def make_test_image() -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    handle.close()
    path = Path(handle.name)
    image = Image.new("RGB", (420, 280), "#f7f7f4")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((80, 80, 340, 190), radius=18, fill="#246fd0", outline="#222222", width=8)
    draw.rounded_rectangle((120, 105, 300, 165), radius=10, fill="#f5f5ef", outline="#333333", width=5)
    draw.ellipse((155, 123, 180, 148), fill="#222222")
    draw.ellipse((220, 123, 245, 148), fill="#222222")
    image.save(path)
    return path


def main() -> int:
    image_path = make_test_image()
    try:
        keyword_response = multipart_upload(image_path)
    finally:
        image_path.unlink(missing_ok=True)

    assert keyword_response["status"] == "success"
    assert keyword_response["keywords"], keyword_response
    assert keyword_response["detected"].get("dominant_color"), keyword_response
    assert keyword_response["detected"].get("connector_type"), keyword_response
    assert "job_id" not in keyword_response, "image keyword endpoint must not create CAD jobs"
    assert "files" not in keyword_response, "image keyword endpoint must not create CAD/SOP files"

    first_keyword = keyword_response["keywords"][0]
    search_response = request_json(
        "POST",
        "/api/procurement/search",
        {
            "query": first_keyword,
            "target_location": "浙江 宁波",
            "platforms": ["淘宝", "京东", "1688", "其他"],
            "sort_by": "match",
            "image_search_enabled": True,
            "source_types": ["mock"],
        },
    )
    assert search_response["status"] == "success"
    assert len(search_response["results"]) >= 1

    print("PROCUREMENT_IMAGE_KEYWORDS_ACCEPTANCE_PASS")
    print(f"keyword={first_keyword}")
    print(f"results={len(search_response['results'])}")
    print(f"confidence={keyword_response['confidence']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"PROCUREMENT_IMAGE_KEYWORDS_ACCEPTANCE_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
