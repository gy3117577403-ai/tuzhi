from __future__ import annotations

from urllib.parse import urlparse

APPROVED_DOMAINS = {
    "te.com": {"category": "official_manufacturer", "name": "TE Connectivity"},
    "molex.com": {"category": "official_manufacturer", "name": "Molex"},
    "amphenol.com": {"category": "official_manufacturer", "name": "Amphenol"},
    "digikey.com": {"category": "authorized_distributor", "name": "Digi-Key"},
    "mouser.com": {"category": "authorized_distributor", "name": "Mouser"},
    "traceparts.com": {"category": "third_party_repository", "name": "TraceParts"},
    "3dcontentcentral.com": {"category": "third_party_repository", "name": "3D ContentCentral"},
    "local-test": {"category": "local_test", "name": "Local Test Asset"},
}


def classify_source_url(url: str) -> dict:
    domain = _extract_domain(url)
    for approved_domain, metadata in APPROVED_DOMAINS.items():
        if domain == approved_domain or domain.endswith(f".{approved_domain}"):
            return {
                "domain": approved_domain,
                "category": metadata["category"],
                "name": metadata["name"],
                "is_approved": True,
                "warning": "",
            }
    return {
        "domain": domain,
        "category": "unknown",
        "name": "",
        "is_approved": False,
        "warning": "Unknown CAD source domain. Manual verification required before production use.",
    }


def _extract_domain(url: str) -> str:
    if not url:
        return ""
    if url == "local-test":
        return "local-test"
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return "local-test"
    host = parsed.netloc or parsed.path.split("/")[0]
    host = host.lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host
