from __future__ import annotations

import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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


def request_text(path: str) -> str:
    req = Request(f"{BASE_URL}{path}", headers={"Accept": "text/csv"}, method="GET")
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8-sig")


def search(sort_by: str) -> dict:
    return request_json(
        "POST",
        "/api/procurement/search",
        {
            "query": "1-968970-1",
            "target_location": "浙江 宁波",
            "platforms": ["淘宝", "京东", "1688", "其他"],
            "sort_by": sort_by,
            "image_search_enabled": False,
        },
    )


def assert_result_fields(item: dict) -> None:
    required = [
        "title",
        "platform",
        "price",
        "shipping_location",
        "image_url",
        "key_parameters",
        "match_score",
        "risk_tags",
        "product_url",
    ]
    missing = [field for field in required if field not in item]
    assert not missing, f"result missing fields: {missing}"


def main() -> int:
    price_response = search("price")
    assert price_response["status"] == "success"
    assert len(price_response["results"]) >= 1
    for item in price_response["results"]:
        assert_result_fields(item)

    assert price_response["results"][0]["price_type"] != "abnormal", "abnormal price ranked first"
    normal_prices = [item["price"] for item in price_response["results"] if item["price_type"] != "abnormal"]
    assert normal_prices == sorted(normal_prices), f"normal prices not ascending: {normal_prices}"

    location_response = search("location")
    assert location_response["results"], "location search returned no results"
    top_location = location_response["results"][0]["shipping_location"]
    assert "浙江" in top_location or "宁波" in top_location, f"location sort did not prioritize target: {top_location}"

    csv_text = request_text(f"/api/procurement/search/{price_response['search_id']}/export.csv")
    assert "title" in csv_text and "platform" in csv_text and "price" in csv_text, "CSV export missing expected columns"

    print("SINGLE_PROCUREMENT_UI_ACCEPTANCE_PASS")
    print(f"search_id={price_response['search_id']}")
    print(f"results={len(price_response['results'])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"SINGLE_PROCUREMENT_UI_ACCEPTANCE_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
