from __future__ import annotations

import hashlib
import hmac
import json
import os
from copy import deepcopy
from typing import Any

SIGNATURE_FIELDS = {"payload_hash", "signature", "signature_algorithm", "signature_warning"}
DEV_WARNING = "Using development audit signing secret. Configure AUDIT_SIGNING_SECRET for production."


def canonicalize_event_payload(event: dict[str, Any]) -> str:
    payload = {key: value for key, value in deepcopy(event).items() if key not in SIGNATURE_FIELDS}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_payload_hash(event: dict[str, Any]) -> str:
    return hashlib.sha256(canonicalize_event_payload(event).encode("utf-8")).hexdigest()


def sign_event(event: dict[str, Any]) -> dict[str, Any]:
    secret, warning = _secret()
    payload_hash = compute_payload_hash(event)
    signature = hmac.new(secret.encode("utf-8"), payload_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        **event,
        "payload_hash": payload_hash,
        "signature": signature,
        "signature_algorithm": "HMAC-SHA256",
        "signature_warning": warning,
    }


def verify_event_signature(event: dict[str, Any]) -> dict[str, Any]:
    if not event.get("signature") or not event.get("payload_hash"):
        return _result(event, "unsigned_legacy", "Event has no signature.")
    expected_hash = compute_payload_hash(event)
    if expected_hash != event.get("payload_hash"):
        return _result(event, "invalid", "Payload hash mismatch.")
    secret, _ = _secret()
    expected_signature = hmac.new(secret.encode("utf-8"), expected_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, event.get("signature", "")):
        return _result(event, "invalid", "Signature mismatch.")
    return _result(event, "valid", "Signature verified.")


def _result(event: dict[str, Any], status: str, message: str) -> dict[str, Any]:
    return {
        "event_id": event.get("id", ""),
        "registry_item_id": event.get("registry_item_id", ""),
        "event_type": event.get("event_type", ""),
        "status": status,
        "message": message,
    }


def _secret() -> tuple[str, str]:
    secret = os.getenv("AUDIT_SIGNING_SECRET")
    if secret:
        return secret, ""
    return "dev-local-audit-signing-secret", DEV_WARNING
