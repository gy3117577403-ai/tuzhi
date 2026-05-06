from __future__ import annotations

import csv
import io
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "http://127.0.0.1:8000"


def request_json(method: str, path: str, payload: dict | None = None) -> dict:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"{method} {path} failed: HTTP {exc.code} {detail}") from exc
    except URLError as exc:
        raise AssertionError(f"{method} {path} failed: {exc}") from exc


def request_text(path: str) -> str:
    req = Request(f"{BASE_URL}{path}", headers={"Accept": "text/csv"}, method="GET")
    try:
        with urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8-sig")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"GET {path} failed: HTTP {exc.code} {detail}") from exc
    except URLError as exc:
        raise AssertionError(f"GET {path} failed: {exc}") from exc


def search(sort_by: str, platforms: list[str] | None = None) -> dict:
    return request_json(
        "POST",
        "/api/procurement/search",
        {
            "query": "1-968970-1",
            "target_location": "浙江 宁波",
            "platforms": platforms or ["淘宝", "京东", "1688", "其他"],
            "sort_by": sort_by,
            "image_search_enabled": False,
        },
    )


def assert_price_sort(results: list[dict]) -> None:
    assert results, "price sort returned no results"
    assert results[0]["price_type"] != "abnormal", "abnormal price item must not rank first"
    normal_prices = [item["price"] for item in results if item["price_type"] != "abnormal"]
    assert normal_prices == sorted(normal_prices), f"normal prices are not ascending: {normal_prices}"


def assert_location_sort(results: list[dict]) -> None:
    assert results, "location sort returned no results"
    top_location = results[0]["shipping_location"]
    assert "浙江" in top_location or "宁波" in top_location, f"top result is not near target location: {top_location}"
    assert results[0]["price_type"] != "abnormal", "abnormal price item must not rank first for location sort"


def assert_match_sort(results: list[dict]) -> None:
    assert results, "match sort returned no results"
    top_score = results[0]["match_score"]
    assert all(top_score >= item["match_score"] for item in results), "top result is not highest match score"


def assert_csv(search_id: str) -> None:
    csv_text = request_text(f"/api/procurement/search/{search_id}/export.csv")
    assert "title" in csv_text, "CSV header missing title"
    assert "platform" in csv_text, "CSV header missing platform"
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) >= 8, f"CSV expected at least 8 rows, got {len(rows)}"


def main() -> int:
    price_response = search("price")
    assert price_response["status"] == "success"
    assert len(price_response["results"]) >= 8
    assert price_response["summary"]["total"] >= 8
    assert price_response["warnings"], "expected procurement search warning"
    assert_price_sort(price_response["results"])

    fetched = request_json("GET", f"/api/procurement/search/{price_response['search_id']}")
    assert fetched["search_id"] == price_response["search_id"]
    assert len(fetched["results"]) == len(price_response["results"])
    assert_csv(price_response["search_id"])

    location_response = search("location")
    assert_location_sort(location_response["results"])

    match_response = search("match")
    assert_match_sort(match_response["results"])

    jd_response = search("price", ["京东"])
    assert jd_response["results"], "京东 platform filter returned no results"
    assert all(item["platform"] == "京东" for item in jd_response["results"])

    risk_tags = [tag for item in price_response["results"] for tag in item.get("risk_tags", [])]
    assert any("相近型号" in tag for tag in risk_tags), "expected near part-number risk tags"
    assert any("价格异常" in tag for tag in risk_tags), "expected abnormal price risk tag"

    print("PROCUREMENT_ACCEPTANCE_PASS")
    print(f"search_id={price_response['search_id']}")
    print(f"results={len(price_response['results'])}")
    print(f"lowest_price={price_response['summary']['lowest_price']}")
    print(f"recommended_count={price_response['summary']['recommended_count']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"PROCUREMENT_ACCEPTANCE_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
