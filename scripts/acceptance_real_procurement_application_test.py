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
        with urlopen(req, timeout=60) as response:
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


def assert_result(item: dict) -> None:
    assert item.get("title"), "title missing"
    assert "product_url" in item, "product_url missing"
    assert item.get("product_url") or "链接缺失" in item.get("risk_tags", []), "product_url missing without risk tag"
    assert item.get("source_type"), "source_type missing"
    assert "price_verification_status" in item, "price_verification_status missing"
    assert "requires_manual_open" in item, "requires_manual_open missing"
    assert item["requires_manual_open"] is True
    assert any("需打开链接确认" in tag for tag in item.get("risk_tags", [])), "manual-open risk tag missing"
    forbidden = {"confirmed_price", "effective_price", "price_tiers", "confirmed_by"}
    assert not (forbidden & set(item.keys())), f"forbidden fields present: {forbidden & set(item.keys())}"


def main() -> int:
    response = search("price")
    summary = response["summary"].get("provider_summary") or {}
    assert "serpapi_configured" in summary, "provider_summary.serpapi_configured missing"
    if summary["serpapi_configured"]:
        assert summary.get("provider_mode") in {"serpapi", "fallback"}, summary
        if summary.get("provider_mode") == "fallback":
            assert response["warnings"], "fallback must include clear warning"
    else:
        assert summary.get("provider_mode") == "mock", summary
        assert summary.get("fallback_used") is True, summary

    results = response["results"]
    assert len(results) >= 1
    for item in results:
        assert_result(item)
    assert results[0]["price_type"] != "abnormal", "abnormal price must not rank first"

    location_response = search("location")
    assert location_response["results"], "location sort returned no results"
    assert location_response["results"][0]["price_type"] != "abnormal"

    csv_text = request_text(f"/api/procurement/search/{response['search_id']}/export.csv")
    assert "search_summary_price" in csv_text
    assert "requires_manual_open" in csv_text
    for forbidden in ("confirmed_price", "effective_price", "price_tiers", "manual confirmation"):
        assert forbidden not in csv_text, f"CSV contains forbidden field {forbidden}"

    print("REAL_PROCUREMENT_APPLICATION_ACCEPTANCE_PASS")
    print(f"search_id={response['search_id']}")
    print(f"provider_mode={summary.get('provider_mode')}")
    print(f"serpapi_configured={summary.get('serpapi_configured')}")
    print(f"results={len(results)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"REAL_PROCUREMENT_APPLICATION_ACCEPTANCE_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
