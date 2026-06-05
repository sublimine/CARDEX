"""
net_guard — SSRF protection for URLs sourced from untrusted input.

Discovery and extraction follow URLs that originate from attacker-influenced
data: a dealer's robots.txt `Sitemap:` directive, `<loc>` entries inside a
fetched sitemap, WordPress REST `link` fields, or a `domain` column populated
from external registries. Without validation, a hostile dealer can point any of
these at internal infrastructure — most dangerously the cloud metadata endpoint
(169.254.169.254), localhost, or RFC1918 ranges — turning the crawler into an
SSRF pivot.

`is_safe_public_url` rejects:
  * non-http(s) schemes (file://, gopher://, ftp://, …),
  * URLs with no hostname,
  * IP-literal hosts in private / loopback / link-local / reserved / multicast
    / unspecified ranges (covers the metadata service and internal subnets),
  * obvious internal names (localhost, *.localhost, *.internal, *.local).

With ``resolve=True`` it additionally resolves the hostname and rejects the URL
when ANY resolved address is non-public — this closes DNS-rebinding (a public
name that resolves to a private IP) but performs a blocking ``getaddrinfo`` and
fails closed when resolution fails, so callers in tight async loops over
synthetic hosts should keep the default ``resolve=False`` (which still blocks
every IP-literal and internal-name vector).
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = ("http", "https")
_INTERNAL_SUFFIXES = (".localhost", ".internal", ".local")


def _ip_is_public(raw_ip: str) -> bool:
    """True only for a globally routable unicast address."""
    try:
        addr = ipaddress.ip_address(raw_ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def is_safe_public_url(url: str, *, resolve: bool = False) -> bool:
    """
    Return True when `url` is safe to fetch from a server-side crawler.

    Always blocks non-http(s) schemes, missing hosts, private/loopback/link-local
    /reserved IP literals (incl. the 169.254.169.254 metadata service), and
    internal hostnames. With ``resolve=True`` also blocks hostnames that resolve
    to a non-public address (DNS-rebinding), failing closed on resolution error.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return False
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        return False
    host = parts.hostname
    if not host:
        return False

    # IP-literal host: validate the literal directly (strip IPv6 zone id).
    literal = host.split("%", 1)[0]
    try:
        ipaddress.ip_address(literal)
        return _ip_is_public(literal)
    except ValueError:
        pass  # not an IP literal — treat as a DNS name

    low = host.lower().rstrip(".")
    if low == "localhost" or low.endswith(_INTERNAL_SUFFIXES):
        return False
    if "." not in low:
        # Single-label hostnames (e.g. "router", "intranet") only resolve on an
        # internal network — never a legitimate public crawl target.
        return False

    if not resolve:
        return True

    try:
        infos = socket.getaddrinfo(host, parts.port or None, proto=socket.IPPROTO_TCP)
    except OSError:
        return False  # fail closed: unresolvable host is not fetched
    if not infos:
        return False
    return all(_ip_is_public(info[4][0]) for info in infos)
