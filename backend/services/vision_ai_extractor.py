from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from services.ai_client import is_ai_configured, safe_chat_completions

SYSTEM_PROMPT = """You analyze connector product photos for approximate appearance classification only.

Rules:
- Do NOT invent millimeter dimensions.
- Output a single JSON object with keys:
  likely_connector_family (string),
  likely_positions (integer or null),
  likely_color (string),
  likely_front_face_layout ({cols:int|null, rows:int|null}|null),
  likely_latch_style (string),
  confidence ("low"|"medium"|"high"),
  notes (string).

Describe appearance only — not manufacturing measurements."""

DEFAULT_VISION: dict[str, Any] = {
    "likely_connector_family": "",
    "likely_positions": None,
    "likely_color": "",
    "likely_front_face_layout": None,
    "likely_latch_style": "",
    "confidence": "low",
    "notes": "",
}


def _parse_json_obj(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        if "```" in raw:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1:
                try:
                    data = json.loads(raw[start : end + 1])
                    return data if isinstance(data, dict) else None
                except json.JSONDecodeError:
                    pass
    return None


def extract_vision_analysis(
    image_path: str | Path,
    text_context: str | None,
    image_features_summary: dict[str, Any],
) -> dict[str, Any]:
    """
    Prefer multimodal request when API accepts images; otherwise text-only structured inference.
    Never raises — returns default-shaped dict on failure.
    """
    summary_txt = json.dumps(image_features_summary, ensure_ascii=False)
    user_text = (
        f"Optional user text: {(text_context or '').strip()}\n\n"
        f"OpenCV-derived image_features summary (approximate):\n{summary_txt}\n\n"
        "Respond with JSON only."
    )

    path = Path(image_path)
    mime = "image/jpeg"
    suf = path.suffix.lower()
    if suf in {".png"}:
        mime = "image/png"
    elif suf in {".webp"}:
        mime = "image/webp"

    content, err = None, None
    if path.exists() and is_ai_configured():
        raw = path.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]
        content, err = safe_chat_completions(messages)  # type: ignore[arg-type]
        if err or not (content or "").strip():
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ]
            content, err = safe_chat_completions(messages)

    elif is_ai_configured():
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]
        content, err = safe_chat_completions(messages)
    else:
        out = {**DEFAULT_VISION}
        out["notes"] = "AI API is not configured; vision analysis skipped."
        return out

    parsed = _parse_json_obj(content or "") if content else None
    if not parsed:
        out = {**DEFAULT_VISION}
        out["notes"] = (err or "Vision model returned non-JSON.")[:300]
        return out

    merged = {**DEFAULT_VISION, **parsed}
    return merged
