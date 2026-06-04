"""
Coherence enforcer — garantiza que todos los campos de una identidad son
mutuamente coherentes antes de usarla. Cualquier incoherencia → CoherenceError y
la sesión NO se inicia (SCRAPING_ENGINE.md §A1 + §A4 protocolo de carga).

Creation checks:
  - tcp_profile OS == User-Agent OS         (Chrome/Windows → windows_11)
  - tls_profile browser == User-Agent browser
  - timezone == country timezone
  - locale == country locale
  - webrtc_ip == proxy_ip                   (WebRTC filtra la IP del proxy)

Pre-session checks (en cada carga):
  - las invariantes de creación siguen vigentes
  - storage_state, si existe, es JSON Playwright parseable (no corrupto)
"""
from __future__ import annotations

import json

from scrapers.engine.identity.profile import (
    COUNTRY_LOCALES,
    COUNTRY_TIMEZONES,
    Identity,
    TCPProfile,
    TLSProfile,
)


class CoherenceError(ValueError):
    """Identity has incoherent fields. Do not use for scraping."""


_TCP_OS: dict[TCPProfile, str] = {
    TCPProfile.WINDOWS_11: "windows",
    TCPProfile.MACOS_14: "macos",
    TCPProfile.UBUNTU_22: "linux",
}

_TLS_BROWSER: dict[TLSProfile, str] = {
    TLSProfile.CHROME136: "chrome",
    TLSProfile.FIREFOX147: "firefox",
    TLSProfile.SAFARI260: "safari",
}


def ua_os(user_agent: str) -> str:
    """Derive the OS family advertised by a User-Agent string."""
    if "Windows NT" in user_agent:
        return "windows"
    if "Mac OS X" in user_agent or "Macintosh" in user_agent:
        return "macos"
    if "Linux" in user_agent or "X11" in user_agent:
        return "linux"
    return "unknown"


def ua_browser(user_agent: str) -> str:
    """Derive the browser advertised by a User-Agent string. Order matters."""
    if "Firefox/" in user_agent:
        return "firefox"
    if "Edg/" in user_agent:
        return "edge"
    if "Chrome/" in user_agent:
        return "chrome"
    if "Safari/" in user_agent and "Version/" in user_agent:
        return "safari"
    return "unknown"


def validate_creation(identity: Identity) -> None:
    """Raise CoherenceError if identity fields are incoherent at creation time."""
    fp = identity.fingerprint
    if fp is None:
        raise CoherenceError("identity has no fingerprint")

    expected_os = _TCP_OS[identity.tcp_profile]
    actual_os = ua_os(fp.user_agent)
    if actual_os != expected_os:
        raise CoherenceError(
            f"tcp_profile={identity.tcp_profile.value} implies OS {expected_os!r} "
            f"but user_agent advertises {actual_os!r}"
        )

    expected_browser = _TLS_BROWSER[identity.tls_profile]
    actual_browser = ua_browser(fp.user_agent)
    if actual_browser != expected_browser:
        raise CoherenceError(
            f"tls_profile={identity.tls_profile.value} implies browser "
            f"{expected_browser!r} but user_agent advertises {actual_browser!r}"
        )

    tz = COUNTRY_TIMEZONES.get(identity.country)
    if tz is None:
        raise CoherenceError(f"unsupported country {identity.country!r}")
    if fp.timezone != tz:
        raise CoherenceError(
            f"country {identity.country} requires timezone {tz!r}, got {fp.timezone!r}"
        )

    locale = COUNTRY_LOCALES.get(identity.country)
    if fp.locale != locale:
        raise CoherenceError(
            f"country {identity.country} requires locale {locale!r}, got {fp.locale!r}"
        )

    if fp.webrtc_ip != identity.proxy_ip:
        raise CoherenceError(
            f"webrtc_ip {fp.webrtc_ip!r} must equal proxy_ip {identity.proxy_ip!r} "
            "(WebRTC would otherwise leak a mismatched IP)"
        )


def validate_pre_session(identity: Identity, domain: str) -> None:
    """Raise CoherenceError if identity is not safe to use for this domain now."""
    validate_creation(identity)

    if identity.storage_state is not None:
        try:
            raw = identity.storage_state
            json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise CoherenceError(f"storage_state for {domain} is corrupt: {exc}") from exc
