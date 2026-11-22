"""Text and URL canonicalisation helpers used by news ingestion."""
from __future__ import annotations
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"}

def canonicalize_url(url: str) -> str:
    """Normalise a URL and remove common tracking parameters."""
    value = (url or "").strip()
    parts = urlsplit(value)
    scheme = (parts.scheme or "https").lower()
    hostname = (parts.hostname or "").lower()
    if not hostname:
        return value.split("#", 1)[0]
    port = parts.port
    netloc = hostname
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    query = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in _TRACKING_KEYS:
            continue
        query.append((key, val))
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query)), ""))

def normalize_title(title: str) -> str:
    """Lowercase a title and collapse punctuation/whitespace."""
    value = (title or "").casefold()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())

def sha256_hex(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def extract_plain_url(value: str) -> str:
    """Extract a valid HTTP(S) URL from a plain or matching Markdown link."""
    value = (value or "").strip()

    # Accept Markdown only when its displayed URL matches its destination.
    match = re.fullmatch(
        r"\[(https?://[^\]\s]+)\]\((https?://[^)\s]+)\)",
        value,
        flags=re.IGNORECASE,
    )

    if match:
        label, destination = match.groups()
        if label != destination:
            return ""
        value = destination

    if not value.lower().startswith(("http://", "https://")):
        return ""

    from urllib.parse import urlsplit

    parts = urlsplit(value)
    if not parts.hostname or any(char.isspace() for char in value):
        return ""

    return value
