from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path
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
        raise AssertionError(f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}") from exc
    except URLError as exc:
        raise AssertionError(str(exc)) from exc


def request_text(path: str) -> str:
    req = Request(f"{BASE_URL}{path}", headers={"Accept": "text/csv"}, method="GET")
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8-sig")


def multipart_upload(path: Path, content_type: str) -> dict:
    boundary = "----procurement-import-boundary"
    file_bytes = path.read_bytes()
    parts = [
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="source_name"\r\n\r\n'
            "验收临时报价表\r\n"
        ).encode("utf-8"),
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="platform_label"\r\n\r\n'
            "其他\r\n"
        ).encode("utf-8"),
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8"),
        file_bytes,
        f"\r\n--{boundary}--\r\n".encode("utf-8"),
    ]
    req = Request(
        f"{BASE_URL}/api/procurement/import",
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def make_temp_csv() -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".csv", encoding="utf-8-sig", newline="", delete=False)
    with handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["商品标题", "平台", "供应商", "价格", "币种", "发货地", "库存", "起订量", "商品链接", "图片链接", "品牌", "型号", "孔位", "颜色", "类型"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "商品标题": "1-968970-1 授权供应商现货报价",
                "平台": "其他",
                "供应商": "宁波授权连接器供应商",
                "价格": "2.35",
                "币种": "CNY",
                "发货地": "浙江 宁波",
                "库存": "现货 500 件",
                "起订量": "20",
                "商品链接": "https://example.com/imported/1-968970-1",
                "图片链接": "",
                "品牌": "TE",
                "型号": "1-968970-1",
                "孔位": "4P",
                "颜色": "蓝色",
                "类型": "汽车连接器",
            }
        )
        writer.writerow(
            {
                "商品标题": "8-968970-1 相近型号报价",
                "平台": "其他",
                "供应商": "临时报价供应商",
                "价格": "1.85",
                "币种": "CNY",
                "发货地": "江苏 苏州",
                "库存": "需确认",
                "起订量": "100",
                "商品链接": "https://example.com/imported/8-968970-1",
                "图片链接": "",
                "品牌": "TE",
                "型号": "8-968970-1",
                "孔位": "4P",
                "颜色": "蓝色",
                "类型": "汽车连接器",
            }
        )
    return Path(handle.name)


def make_temp_xlsx() -> Path:
    from openpyxl import Workbook

    handle = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    handle.close()
    path = Path(handle.name)
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["商品标题", "平台", "供应商", "价格", "币种", "发货地", "库存", "起订量", "商品链接", "品牌", "型号", "孔位", "颜色", "类型"])
    sheet.append([
        "1-968970-1 Excel 报价样例",
        "其他",
        "Excel 临时供应商",
        2.75,
        "CNY",
        "浙江 宁波",
        "现货 300 件",
        10,
        "https://example.com/imported/xlsx-1-968970-1",
        "TE",
        "1-968970-1",
        "4P",
        "蓝色",
        "汽车连接器",
    ])
    workbook.save(path)
    return path


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
            "source_types": ["mock", "csv_upload", "excel_upload"],
        },
    )


def main() -> int:
    csv_path = make_temp_csv()
    try:
        imported = multipart_upload(csv_path, "text/csv")
    finally:
        csv_path.unlink(missing_ok=True)

    xlsx_path = make_temp_xlsx()
    try:
        excel_imported = multipart_upload(xlsx_path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    finally:
        xlsx_path.unlink(missing_ok=True)

    assert imported["rows_imported"] > 0, imported
    assert imported["rows_skipped"] == 0, imported
    assert excel_imported["rows_imported"] > 0, excel_imported

    price_response = search("price")
    imported_results = [item for item in price_response["results"] if item.get("source_type") in {"csv_upload", "excel_upload"}]
    assert imported_results, "search results did not include imported offers"
    assert any("授权供应商现货报价" in item["title"] for item in imported_results), "CSV imported offer missing from results"
    assert any("Excel 报价样例" in item["title"] for item in imported_results), "Excel imported offer missing from results"
    assert price_response["results"][0]["price_type"] != "abnormal", "abnormal price ranked first"

    location_response = search("location")
    assert "浙江" in location_response["results"][0]["shipping_location"], "location sort did not prioritize target province"

    csv_text = request_text(f"/api/procurement/search/{price_response['search_id']}/export.csv")
    assert "授权供应商现货报价" in csv_text, "export CSV missing imported offer"
    assert "csv_upload" in csv_text, "export CSV missing source_type"

    sources = request_json("GET", "/api/procurement/sources")
    assert any(source["source_type"] == "csv_upload" for source in sources["sources"]), "csv source not listed"
    assert any(source["source_type"] == "excel_upload" for source in sources["sources"]), "excel source not listed"

    print("PROCUREMENT_IMPORT_ACCEPTANCE_PASS")
    print(f"csv_import_id={imported['import_id']}")
    print(f"excel_import_id={excel_imported['import_id']}")
    print(f"rows_imported={imported['rows_imported'] + excel_imported['rows_imported']}")
    print(f"search_id={price_response['search_id']}")
    print(f"imported_results={len(imported_results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
