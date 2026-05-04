from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_ENV_PATH = _BACKEND_ROOT / ".env"
load_dotenv(_ENV_PATH)


class AiApiNotConfiguredError(Exception):
    """Raised when CONNECTOR_AI_* env vars are incomplete."""

    def __init__(self, message: str = "AI API is not configured.") -> None:
        super().__init__(message)


def _strip_trailing_slash(url: str) -> str:
    return url.rstrip("/")


def get_ai_env() -> dict[str, str]:
    """Read AI-related settings from environment (after dotenv load)."""
    base = (os.getenv("CONNECTOR_AI_API_BASE_URL") or "").strip()
    key = (os.getenv("CONNECTOR_AI_API_KEY") or os.getenv("CONNECTOR_CAD_API_KEY") or "").strip()
    model = (os.getenv("CONNECTOR_AI_MODEL") or "").strip()
    provider = (os.getenv("CONNECTOR_AI_PROVIDER") or "openai_compatible").strip() or "openai_compatible"
    return {
        "base_url": base,
        "api_key": key,
        "model": model,
        "provider": provider,
    }


def is_ai_configured() -> bool:
    env = get_ai_env()
    return bool(env["base_url"] and env["api_key"] and env["model"])


def require_ai_config() -> dict[str, str]:
    env = get_ai_env()
    if not (env["base_url"] and env["api_key"] and env["model"]):
        raise AiApiNotConfiguredError("AI API is not configured.")
    return env


def preview_api_key(key: str) -> str:
    """Show first/last few characters only; never the full key."""
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:3]}****{key[-3:]}"


def chat_completions(
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.1,
    timeout_sec: float = 90.0,
) -> str:
    """
    OpenAI-compatible chat completions. POST {base}/chat/completions
    Authorization: Bearer {key}
    """
    env = require_ai_config()
    url = f"{_strip_trailing_slash(env['base_url'])}/chat/completions"
    headers = {
        "Authorization": f"Bearer {env['api_key']}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": env["model"],
        "messages": messages,
        "temperature": temperature,
    }
    with httpx.Client(timeout=timeout_sec) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return ""


def _transient_ai_transport_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    hints = (
        "ssl",
        "eof",
        "disconnected",
        "timeout",
        "connection reset",
        "connection aborted",
        "broken pipe",
        "remote protocol",
    )
    return any(h in msg for h in hints)


def safe_chat_completions(messages: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """
    Never raises for HTTP/network errors; returns (content, error_message).
    AiApiNotConfiguredError is returned as error string, not raised.
    Retries a few times on transient TLS / connection drops.
    """
    last_error: str | None = None
    for attempt in range(3):
        try:
            return chat_completions(messages), None
        except AiApiNotConfiguredError as exc:
            return None, str(exc)
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                detail = exc.response.text[:500]
            except Exception:
                detail = ""
            return None, f"HTTP {exc.response.status_code}: {detail or str(exc)}"
        except Exception as exc:
            last_error = str(exc)
            if attempt < 2 and _transient_ai_transport_error(exc):
                time.sleep(0.4 * (attempt + 1))
                continue
            return None, last_error
    return None, last_error


def parse_json_object_from_llm(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from model output (raw or fenced)."""
    raw = (text or "").strip()
    if not raw:
        return None
    fence = "```"
    if fence in raw:
        start = raw.find(fence)
        if start != -1:
            after = raw[start + len(fence) :]
            if after.lower().startswith("json"):
                after = after[4:].lstrip()
            end = after.find(fence)
            if end != -1:
                raw = after[:end].strip()
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    brace = raw.find("{")
    if brace != -1:
        tail = raw[brace:]
        for end in range(len(tail), 0, -1):
            chunk = tail[:end]
            try:
                parsed = json.loads(chunk)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
    return None
