"""SSRF / URL scheme guard.

Used before urllib.request.urlopen() to close Bandit B310:
  "Audit url open for permitted schemes. Allowing use of file:/ or
   custom schemes is often unexpected."

Rejects anything except http:// and https://. Optionally rejects
private / link-local IPs to further harden SSRF.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = frozenset({"http", "https"})


class UnsafeURLError(ValueError):
    """Raised when a URL would open an unsafe scheme or target."""


def assert_safe_http_url(url: str, *, allow_private: bool = False) -> str:
    """Validate that ``url`` is an http(s) URL to a public host.

    Args:
        url: URL string to validate.
        allow_private: If True, allow RFC1918 / loopback / link-local targets.
            Default False for SSRF protection on external fetches.

    Returns:
        The URL, unchanged, if it passes.

    Raises:
        UnsafeURLError: if scheme is not http/https, or host is missing, or
            (when ``allow_private`` is False) the host resolves to a private
            address.
    """
    if not isinstance(url, str) or not url:
        raise UnsafeURLError("empty URL")
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"scheme not allowed: {parsed.scheme!r}")
    if not parsed.hostname:
        raise UnsafeURLError("missing hostname")

    if allow_private:
        return url

    # Best-effort SSRF guard: refuse private / link-local / loopback / reserved
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 80)
    except socket.gaierror as e:
        raise UnsafeURLError(f"dns lookup failed: {e}") from e
    for _family, _type, _proto, _canon, sockaddr in infos:
        ip = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            raise UnsafeURLError(
                f"target resolves to non-public address {ip} for host {parsed.hostname}"
            )
    return url
