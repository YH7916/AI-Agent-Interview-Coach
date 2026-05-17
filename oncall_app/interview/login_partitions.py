"""YouNavi-style login profile routing for authorized source collection."""

from __future__ import annotations

import re

from oncall_app.interview.store import InterviewStore
from oncall_app.interview.web_login import normalize_host

MULTI_PART_PUBLIC_SUFFIXES = {
    "com.cn",
    "net.cn",
    "org.cn",
    "com.au",
    "co.uk",
}


def resolve_profile_host(store: InterviewStore, host: str) -> str | None:
    """Return the logged-in host whose browser profile should be reused."""
    raw_host = _raw_host(host)
    if raw_host and store.get_web_login(raw_host) is not None:
        store.touch_web_login(raw_host)
        return raw_host
    normalized = normalize_host(host)
    if not normalized:
        return None
    if store.get_web_login(normalized) is not None:
        store.touch_web_login(normalized)
        return normalized

    domain = registrable_domain(normalized)
    if not domain or domain == normalized:
        return None

    sibling = store.find_sibling_web_login(domain, exclude_host=normalized)
    if sibling:
        store.touch_web_login(sibling)
    return sibling


def registrable_domain(host: str) -> str:
    """Return a pragmatic registrable domain for login-profile sibling lookup."""
    normalized = normalize_host(host).strip(".")
    parts = [part for part in normalized.split(".") if part]
    if len(parts) <= 2:
        return normalized
    suffix = ".".join(parts[-2:])
    if suffix in MULTI_PART_PUBLIC_SUFFIXES and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def profile_partition_name(host: str) -> str:
    """Return the stable profile partition name used by source collection."""
    safe = re.sub(r"[^a-z0-9]+", "-", normalize_host(host).lower()).strip("-")
    return f"web-fetch-{safe}"


def _raw_host(host: str) -> str:
    return host.strip().removeprefix("https://").removeprefix("http://").split("/")[0].split(":")[0].lower()
