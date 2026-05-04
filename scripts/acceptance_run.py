"""One-off E2E checks (avoid PowerShell HEAD quirks)."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parents[1]
PHOTO = ROOT / "backend" / "test_assets" / "sample_connector_photo.png"


def post_json(obj: dict) -> dict:
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/connector-cad/jobs",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def get_params(job_id: str) -> dict:
    url = f"{BASE}/api/connector-cad/jobs/{job_id}/files/params.json"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def head_ok(job_id: str, fname: str) -> tuple[bool, str]:
    req = urllib.request.Request(f"{BASE}/api/connector-cad/jobs/{job_id}/files/{fname}", method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200, str(r.status)
    except urllib.error.HTTPError as e:
        return False, str(e.code)
    except Exception as e:
        return False, repr(e)


def post_photo(path: Path) -> dict:
    boundary = "----PythonAcceptanceBoundary"
    body_parts: list[bytes] = []
    for name, val in [("input_type", "photo")]:
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body_parts.append(val.encode() + b"\r\n")
    raw = path.read_bytes()
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode()
    )
    body_parts.append(b"Content-Type: image/png\r\n\r\n")
    body_parts.append(raw + b"\r\n")
    body_parts.append(f"--{boundary}--\r\n".encode())
    data = b"".join(body_parts)
    req = urllib.request.Request(
        f"{BASE}/api/connector-cad/jobs",
        data=data,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    out: dict = {}

    j1 = post_json({"input_type": "text", "text": "1-968970-1"})
    p1 = get_params(j1["job_id"])
    out["test1"] = {
        "job_id": j1["job_id"],
        "model_origin": p1.get("model_origin"),
        "template_name": p1.get("template_name"),
        "base_color": (p1.get("preview_style") or {}).get("base_color"),
        "pass": p1.get("model_origin") == "series_template"
        and p1.get("template_name") == "TE_BLUE_MULTI_CAVITY"
        and (p1.get("preview_style") or {}).get("base_color") == "blue",
    }

    j2 = post_json({"input_type": "text", "text": "LOCAL SAMPLE STEP"})
    p2 = get_params(j2["job_id"])
    out["test2"] = {
        "job_id": j2["job_id"],
        "model_origin": p2.get("model_origin"),
        "ai_status": (p2.get("ai_extraction") or {}).get("status"),
        "pass": p2.get("model_origin") == "official_cad",
    }

    j3 = post_json(
        {
            "input_type": "text",
            "text": "2 pin rectangular connector pitch 6.0mm body length 36mm body width 18mm",
        }
    )
    p3 = get_params(j3["job_id"])
    ext = (p3.get("ai_extraction") or {}).get("extracted") or {}
    pass3 = (
        p3.get("model_origin") != "official_cad"
        and (p3.get("ai_extraction") or {}).get("status") == "success"
    )
    out["test3"] = {
        "job_id": j3["job_id"],
        "model_origin": p3.get("model_origin"),
        "ai_status": (p3.get("ai_extraction") or {}).get("status"),
        "positions": ext.get("positions"),
        "pitch_mm": ext.get("pitch_mm"),
        "pass": pass3,
    }

    if not PHOTO.exists():
        out["test4"] = {"error": f"missing {PHOTO}"}
    else:
        j4 = post_photo(PHOTO)
        p4 = get_params(j4["job_id"])
        ok_feat, _ = head_ok(j4["job_id"], "image_features.json")
        ok_vis, _ = head_ok(j4["job_id"], "vision_report.json")
        mo = p4.get("model_origin")
        pass4 = mo in ("image_approximated", "generic_mvp") and ok_feat and ok_vis and mo != "official_cad"
        out["test4"] = {
            "job_id": j4["job_id"],
            "model_origin": mo,
            "image_features_200": ok_feat,
            "vision_report_200": ok_vis,
            "pass": pass4,
        }

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if all(
        out[k].get("pass") for k in ("test1", "test2", "test3", "test4") if k in out and "pass" in out[k]
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
