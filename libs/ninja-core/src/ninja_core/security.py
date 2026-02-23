"""Shared network security utilities for SSRF protection and credential redaction."""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse


class SSRFError(ValueError):
    """Raised when a connection string targets a blocked network address."""


# Pattern matches user:password@ in connection URLs.
_CREDENTIAL_RE = re.compile(r"://([^@/]+)@")


def redact_url(url: str) -> str:
    """Replace credentials in a connection URL with ``***:***``.

    Any ``scheme://user:password@host`` segment is replaced so that
    credentials never leak into logs or error messages.

    >>> redact_url("postgresql+asyncpg://admin:s3cret@db.host:5432/mydb")
    'postgresql+asyncpg://***:***@db.host:5432/mydb'
    >>> redact_url("sqlite+aiosqlite:///:memory:")
    'sqlite+aiosqlite:///:memory:'
    >>> redact_url("mongodb://root:hunter2@mongo.internal:27017/app")
    'mongodb://***:***@mongo.internal:27017/app'
    """
    return _CREDENTIAL_RE.sub("://***:***@", url)


# RFC 1918 private ranges, loopback, link-local, and cloud metadata endpoints.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),  # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]

# Hostnames that must always be blocked regardless of DNS resolution.
_BLOCKED_HOSTNAMES = frozenset(
    {
        "metadata.google.internal",
        "metadata.internal",
    }
)


def check_ssrf(url: str, *, allow_private_hosts: bool = False) -> str | None:
    """Validate that a URL does not target a private/internal network address.

    Args:
        url: The connection URL to validate.
        allow_private_hosts: If ``True``, skip all SSRF checks.  Intended for
            legitimate local development use only.

    Returns:
        An error message string if the URL is blocked, or ``None`` if it is safe.
    """
    if allow_private_hosts:
        return None

    parsed = urlparse(url)
    hostname = parsed.hostname

    if not hostname:
        return None  # Let downstream validators handle missing hostnames.

    # Block well-known metadata hostnames
    hostname_lower = hostname.lower()
    if hostname_lower in _BLOCKED_HOSTNAMES:
        return (
            f"Connection to '{hostname}' is blocked: "
            "cloud metadata endpoints are not allowed. "
            "Use --allow-private-hosts for local development."
        )

    # Try to parse hostname as an IP address directly
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # It's a hostname — resolve it to check the IP
        try:
            resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            addrs = {ipaddress.ip_address(r[4][0]) for r in resolved}
        except (socket.gaierror, OSError):
            # Cannot resolve — allow it through (the connection will fail later)
            return None
        for addr in addrs:
            for network in _BLOCKED_NETWORKS:
                if addr in network:
                    return (
                        f"Connection to '{hostname}' (resolves to {addr}) is blocked: "
                        f"address falls in private/reserved range {network}. "
                        "Use --allow-private-hosts for local development."
                    )
        return None

    # Direct IP address check
    for network in _BLOCKED_NETWORKS:
        if addr in network:
            return (
                f"Connection to '{hostname}' is blocked: "
                f"address falls in private/reserved range {network}. "
                "Use --allow-private-hosts for local development."
            )

    return None
