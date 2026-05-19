"""
TLS session factory — curl_cffi AsyncSession por identity.tls_profile.

Un session = una identidad = un JA3 fingerprint fijo durante toda la sesión.
Nunca cambiar impersonate mid-session (rompe JA3 invariant §22).

Mapeo tls_profile → impersonate:
  chrome136  → "chrome"   (alias = latest, actualmente 136+)
  firefox147 → "firefox"
  safari260  → "safari"
"""
from __future__ import annotations

from curl_cffi.requests import AsyncSession

from scrapers.engine.identity.profile import Identity, TLSProfile

_PROFILE_MAP: dict[TLSProfile, str] = {
    TLSProfile.CHROME136: "chrome",
    TLSProfile.FIREFOX147: "firefox",
    TLSProfile.SAFARI260: "safari",
}


def make_session(identity: Identity) -> AsyncSession:
    """
    Create curl_cffi AsyncSession bound to identity TLS profile + proxy.
    Session-level impersonate only — never per-request.
    http_version=3 for QUIC (Strategy B).
    """
    impersonate = _PROFILE_MAP[identity.tls_profile]
    proxy = identity.proxy_ip  # formatted as http://user:pass@host:port
    return AsyncSession(
        impersonate=impersonate,
        http_version=3,
        proxies={"https": proxy, "http": proxy} if proxy else None,
    )
