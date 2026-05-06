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


def main() -> int:
    response = request_json(
        "POST",
        "/api/procurement/search",
        {
            "query": "1-968970-1",
            "target_location": "浙江 宁波",
            "platforms": ["淘宝", "京东", "1688", "其他"],
            "sort_by": "price",
            "image_search_enabled": False,
            "source_types": ["mock"],
        },
    )
    results = response["results"]
    assert len(results) >= 1
    assert results[0]["price_type"] == "normal", "normal summary price should rank before abnormal/unknown"
    assert results[0]["price"] is not None, "top price sorted result should have a summary price"
    assert results[0]["price_verification_status"] != "confirmed"

    found_unknown = False
    found_normal = False
    for item in results:
        assert "price_type" in item
        assert "price_verification_status" in item
        forbidden = {"confirmed_price", "effective_price", "price_tiers", "confirmed_by", "confirmed_at"}
        assert not (forbidden & set(item.keys())), f"forbidden price confirmation fields present: {forbidden & set(item.keys())}"
        if item.get("price") is None:
            found_unknown = True
            assert item["price_type"] == "unknown"
            assert item["price_verification_status"] == "needs_confirmation"
            assert "价格待确认" in item["risk_tags"]
        else:
            found_normal = True
            assert item["price_verification_status"] == "search_summary_only"
            assert item["price_verification_status"] != "confirmed"
            assert "需打开链接确认" in item["risk_tags"]
        if item["price_type"] == "abnormal":
            assert item is not results[0], "abnormal price must not rank first"
            assert "价格异常" in item["risk_tags"]

    assert found_normal, "expected at least one normal summary price"
    assert found_unknown, "expected at least one price pending result"

    csv_text = request_text(f"/api/procurement/search/{response['search_id']}/export.csv")
    assert "search_summary_price" in csv_text
    assert "price_verification_status" in csv_text
    for forbidden in ("confirmed_price", "effective_price", "price_tiers", "confirmation_note"):
        assert forbidden not in csv_text, f"CSV contains forbidden field {forbidden}"

    print("PROCUREMENT_SUMMARY_PRICE_ACCEPTANCE_PASS")
    print(f"search_id={response['search_id']}")
    print(f"results={len(results)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"PROCUREMENT_SUMMARY_PRICE_ACCEPTANCE_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
