from __future__ import annotations

from typing import Any, Literal

from services.ai_client import get_ai_env, is_ai_configured, parse_json_object_from_llm, safe_chat_completions

DEFAULT_EXTRACTED: dict[str, Any] = {
    "manufacturer": "",
    "part_number": "",
    "connector_type": "",
    "positions": None,
    "pitch_mm": None,
    "body_length_mm": None,
    "body_width_mm": None,
    "body_height_mm": None,
    "cavity_diameter_mm": None,
    "mounting_hole_spacing_mm": None,
    "mounting_hole_diameter_mm": None,
    "confidence": "low",
    "unknown_fields": [],
    "notes": "",
}

NUMERIC_KEYS = (
    "positions",
    "pitch_mm",
    "body_length_mm",
    "body_width_mm",
    "body_height_mm",
    "cavity_diameter_mm",
    "mounting_hole_spacing_mm",
    "mounting_hole_diameter_mm",
)

SYSTEM_PROMPT = """You extract structured connector parameters from user text for CAD generation.

Rules:
- Do NOT invent dimensions. If the user did not clearly state a numeric value, use null for that field.
- If you infer a value without explicit user data, set the top-level confidence field to "low".
- Only use "high" confidence when the user explicitly stated that parameter (with a number where applicable).
- Use "medium" only for clearly implied counts from explicit part families without numeric dimensions (rare).
- Output MUST be a single JSON object only, no markdown, no commentary.
- unknown_fields: list field names that are null or uncertain and need human confirmation.
- notes: brief extraction notes (English or Chinese is fine).

Required JSON shape (all keys must be present):
{
  "manufacturer": "",
  "part_number": "",
  "connector_type": "",
  "positions": null,
  "pitch_mm": null,
  "body_length_mm": null,
  "body_width_mm": null,
  "body_height_mm": null,
  "cavity_diameter_mm": null,
  "mounting_hole_spacing_mm": null,
  "mounting_hole_diameter_mm": null,
  "confidence": "low|medium|high",
  "unknown_fields": [],
  "notes": ""
}
"""


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _normalize_confidence(value: Any) -> Literal["low", "medium", "high"]:
    v = str(value or "").lower().strip()
    if v in {"low", "medium", "high"}:
        return v  # type: ignore[return-value]
    return "low"


def _normalize_extracted(raw: dict[str, Any] | None) -> dict[str, Any]:
    out = {**DEFAULT_EXTRACTED}
    if not raw:
        out["notes"] = "AI returned empty or unparsable JSON."
        return out
    for key in ("manufacturer", "part_number", "connector_type", "notes"):
        if key in raw and raw[key] is not None:
            out[key] = str(raw[key]).strip()
    for key in NUMERIC_KEYS:
        if key not in raw:
            continue
        if key == "positions":
            out[key] = _coerce_int(raw[key])
        else:
            out[key] = _coerce_float(raw[key])
    out["confidence"] = _normalize_confidence(raw.get("confidence"))
    uf = raw.get("unknown_fields")
    if isinstance(uf, list):
        out["unknown_fields"] = [str(x) for x in uf if str(x).strip()]
    return out


def extract_connector_params_with_ai(text: str) -> dict[str, Any]:
    """
    Public API: returns the extraction JSON schema only.
    On failure or missing config, returns a safe default-shaped dict (does not raise).
    """
    extracted, _meta = extract_connector_params_with_ai_detailed(text)
    return extracted


def extract_connector_params_with_ai_detailed(
    text: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Returns (extracted_schema, ai_extraction_block) for params.json / job_payload.

    ai_extraction_block keys: enabled, status, provider, model, error, extracted
    status: success | failed | not_configured
    """
    env = get_ai_env()
    base_block: dict[str, Any] = {
        "enabled": True,
        "status": "not_configured",
        "provider": env.get("provider", "openai_compatible"),
        "model": env.get("model", ""),
        "error": "",
        "extracted": {**DEFAULT_EXTRACTED},
    }

    if not is_ai_configured():
        base_block["status"] = "not_configured"
        base_block["error"] = "AI API is not configured."
        base_block["model"] = ""
        extracted = {**DEFAULT_EXTRACTED, "notes": base_block["error"]}
        base_block["extracted"] = extracted
        return extracted, base_block

    user_prompt = f"User text:\n{(text or '').strip()}\n\nRespond with the JSON object only."
    content, err = safe_chat_completions(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
    if err:
        base_block["status"] = "failed"
        base_block["error"] = err
        extracted = _normalize_extracted(None)
        extracted["notes"] = err
        base_block["extracted"] = extracted
        return extracted, base_block

    parsed = parse_json_object_from_llm(content or "")
    extracted = _normalize_extracted(parsed)
    if not parsed:
        base_block["status"] = "failed"
        base_block["error"] = "AI response was not valid JSON."
        extracted["notes"] = base_block["error"]
        base_block["extracted"] = extracted
        return extracted, base_block

    base_block["status"] = "success"
    base_block["error"] = ""
    base_block["extracted"] = extracted
    return extracted, base_block
