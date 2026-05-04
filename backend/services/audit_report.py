from __future__ import annotations

from datetime import datetime, timezone

from services.audit_signature import DEV_WARNING
from services.cache_integrity import check_registry_cache_integrity
from services.json_store import atomic_write_json
from services.registry_history import list_registry_events, verify_registry_history_signatures
from services.registry_search import get_registry_stats
from services.registry_store import DATA_ROOT


def build_audit_report() -> dict:
    stats = get_registry_stats()
    cache = check_registry_cache_integrity()
    verification = verify_registry_history_signatures()
    warnings = []
    if verification["summary"]["unsigned_legacy"]:
        warnings.append("Some audit history events are unsigned legacy events.")
    if verification["summary"]["invalid"]:
        warnings.append("One or more audit history signatures are invalid.")
    if any(result.get("signature_warning") for result in list_registry_events()[-5:]):
        warnings.append(DEV_WARNING)
    if cache["summary"]["missing"] or cache["summary"]["hash_mismatch"] or cache["summary"]["size_mismatch"]:
        warnings.append("One or more registry cache files require repair.")
    return {
        "report_type": "cad_registry_audit_report",
        "generated_at": _now(),
        "registry_stats": stats,
        "cache_integrity_summary": cache["summary"],
        "signature_verification_summary": verification["summary"],
        "recent_events": list_registry_events()[-20:],
        "warnings": list(dict.fromkeys(warnings)),
    }


def write_audit_report() -> tuple[dict, str]:
    report = build_audit_report()
    exports = DATA_ROOT / "registry_exports"
    exports.mkdir(parents=True, exist_ok=True)
    path = exports / f"audit_report_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
    atomic_write_json(path, report)
    return report, str(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
