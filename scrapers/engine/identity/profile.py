"""
Identity profile generator — coherent fingerprint sets.

An identity is a COHERENT bundle. The fields are never mixed across archetypes:
the OS, browser version, User-Agent, screen, WebGL, font subset, TCP profile and
TLS profile are picked together from one device archetype, then country-coherent
timezone/locale/webrtc are layered on top. See SCRAPING_ENGINE.md §A1 invariants.

This module is self-contained: it does not require BrowserForge or any network
service. The archetype pool is curated from real, common European desktop
configurations so generated identities are statistically plausible. canvas_noise
and audio_noise are deterministic seeds derived from the identity id — the same
identity always produces the same hardware hash across visits (invariant 3).
"""
from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TCPProfile(str, Enum):
    WINDOWS_11 = "windows_11"
    MACOS_14 = "macos_14"
    UBUNTU_22 = "ubuntu_22"


class TLSProfile(str, Enum):
    CHROME136 = "chrome136"
    FIREFOX147 = "firefox147"
    SAFARI260 = "safari260"


class ProxyTier(str, Enum):
    ISP_STICKY = "isp_sticky"
    RESIDENTIAL_ROTATING = "residential_rotating"
    MOBILE = "mobile"


class IdentityStatus(str, Enum):
    NEW = "new"
    WARMING = "warming"
    ACTIVE = "active"
    DEGRADED = "degraded"
    QUARANTINE = "quarantine"
    RETIRED = "retired"


@dataclass
class BrowserFingerprint:
    user_agent: str
    screen: dict[str, int]           # {width, height, colorDepth, pixelRatio}
    webgl: dict[str, str]            # {vendor, renderer}
    fonts: list[str]                 # subset real según OS
    platform: str                    # Win32 | MacIntel | Linux x86_64
    hardware_concurrency: int        # 4|8|12|16
    device_memory: int               # 4|8|16
    timezone: str                    # Europe/Berlin | Europe/Paris | ...
    locale: str                      # de-DE | fr-FR | es-ES | ...
    webrtc_ip: str                   # IP coherente con proxy_ip (mismo país)
    do_not_track: None = None
    canvas_noise: float = 0.0        # seed fijo — mismo hash entre visitas
    audio_noise: float = 0.0         # seed fijo — mismo hash entre visitas


@dataclass
class Identity:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    country: str = ""                 # DE|ES|FR|NL|BE|CH

    # Red
    proxy_ip: str = ""
    proxy_tier: ProxyTier = ProxyTier.ISP_STICKY
    proxy_provider: str = ""          # decodo|oxylabs|bright_data
    tcp_profile: TCPProfile = TCPProfile.WINDOWS_11

    # TLS + HTTP
    tls_profile: TLSProfile = TLSProfile.CHROME136
    http_version: int = 3

    # Browser
    fingerprint: BrowserFingerprint | None = None

    # Sesión
    storage_state: bytes | None = None    # Playwright storageState JSON
    abck_tokens: dict[str, Any] = field(default_factory=dict)
    browsing_history: list[str] = field(default_factory=list)

    # Métricas de vida
    status: IdentityStatus = IdentityStatus.NEW
    trust_score: float = 0.0
    request_count: int = 0
    ban_count: int = 0
    warming_done: bool = False
    created_at: int = 0
    last_used: int | None = None
    quarantine_until: int | None = None
    retired_at: int | None = None
    retire_reason: str | None = None


# ── Country-coherent layers ───────────────────────────────────────────────────

COUNTRY_TIMEZONES: dict[str, str] = {
    "DE": "Europe/Berlin",
    "ES": "Europe/Madrid",
    "FR": "Europe/Paris",
    "NL": "Europe/Amsterdam",
    "BE": "Europe/Brussels",
    "CH": "Europe/Zurich",
}

COUNTRY_LOCALES: dict[str, str] = {
    "DE": "de-DE",
    "ES": "es-ES",
    "FR": "fr-FR",
    "NL": "nl-NL",
    "BE": "fr-BE",
    "CH": "de-CH",
}

_WINDOWS_FONTS = [
    "Arial", "Calibri", "Cambria", "Consolas", "Georgia", "Segoe UI",
    "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana",
]
_MACOS_FONTS = [
    "Helvetica Neue", "Helvetica", "Lucida Grande", "Geneva", "Menlo",
    "Monaco", "Optima", "Gill Sans", "Avenir", "Arial",
]


# A device archetype is a fully coherent hardware/software bundle. Every field is
# consistent with every other (OS↔browser↔WebGL↔platform↔TCP↔TLS). Picking one
# guarantees coherence by construction.
@dataclass(frozen=True)
class _Archetype:
    tcp_profile: TCPProfile
    tls_profile: TLSProfile
    platform: str
    user_agent: str
    webgl_vendor: str
    webgl_renderer: str
    fonts: tuple[str, ...]
    hw_pool: tuple[int, ...]
    mem_pool: tuple[int, ...]
    screens: tuple[tuple[int, int, int], ...]   # (width, height, pixelRatio)


_ARCHETYPES: tuple[_Archetype, ...] = (
    _Archetype(
        TCPProfile.WINDOWS_11, TLSProfile.CHROME136, "Win32",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Google Inc. (Intel)",
        "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        tuple(_WINDOWS_FONTS), (8, 12, 16), (8, 16),
        ((1920, 1080, 1), (2560, 1440, 1), (1536, 864, 1)),
    ),
    _Archetype(
        TCPProfile.WINDOWS_11, TLSProfile.CHROME136, "Win32",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Google Inc. (NVIDIA)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        tuple(_WINDOWS_FONTS), (8, 12, 16), (16,),
        ((1920, 1080, 1), (2560, 1440, 1)),
    ),
    _Archetype(
        TCPProfile.WINDOWS_11, TLSProfile.FIREFOX147, "Win32",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) "
        "Gecko/20100101 Firefox/147.0",
        "Mozilla",
        "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        tuple(_WINDOWS_FONTS), (4, 8, 12), (8, 16),
        ((1920, 1080, 1), (1536, 864, 1)),
    ),
    _Archetype(
        TCPProfile.MACOS_14, TLSProfile.CHROME136, "MacIntel",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Google Inc. (Apple)",
        "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)",
        tuple(_MACOS_FONTS), (8, 10, 12), (8, 16),
        ((1512, 982, 2), (1728, 1117, 2), (1440, 900, 2)),
    ),
    _Archetype(
        TCPProfile.MACOS_14, TLSProfile.SAFARI260, "MacIntel",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/26.0 Safari/605.1.15",
        "Apple Inc.",
        "Apple GPU",
        tuple(_MACOS_FONTS), (8, 10, 12), (8, 16),
        ((1512, 982, 2), (1728, 1117, 2)),
    ),
)


def _seed_from_id(identity_id: str) -> random.Random:
    """Deterministic RNG keyed on the identity id — stable noise across runs."""
    return random.Random(int(uuid.UUID(identity_id).int))


def generate(
    country: str,
    proxy_ip: str,
    proxy_tier: ProxyTier,
    proxy_provider: str = "decodo",
    identity_id: str | None = None,
) -> Identity:
    """
    Generate a coherent Identity for the given country + proxy.

    The fingerprint is a single archetype (no cross-mixing). canvas_noise and
    audio_noise are derived deterministically from the identity id, so the same
    identity always hashes the same hardware. webrtc_ip is pinned to proxy_ip so
    WebRTC leaks the proxy's IP (same country), matching geoip alignment.
    """
    if country not in COUNTRY_TIMEZONES:
        raise ValueError(f"unsupported country: {country!r}")

    iid = identity_id or str(uuid.uuid4())
    rng = _seed_from_id(iid)

    arch = rng.choice(_ARCHETYPES)
    width, height, pixel_ratio = rng.choice(arch.screens)

    fingerprint = BrowserFingerprint(
        user_agent=arch.user_agent,
        screen={
            "width": width,
            "height": height,
            "colorDepth": 24,
            "pixelRatio": pixel_ratio,
        },
        webgl={"vendor": arch.webgl_vendor, "renderer": arch.webgl_renderer},
        fonts=list(arch.fonts),
        platform=arch.platform,
        hardware_concurrency=rng.choice(arch.hw_pool),
        device_memory=rng.choice(arch.mem_pool),
        timezone=COUNTRY_TIMEZONES[country],
        locale=COUNTRY_LOCALES[country],
        webrtc_ip=proxy_ip,
        canvas_noise=rng.uniform(-1e-4, 1e-4),
        audio_noise=rng.uniform(-1e-5, 1e-5),
    )

    return Identity(
        id=iid,
        country=country,
        proxy_ip=proxy_ip,
        proxy_tier=proxy_tier,
        proxy_provider=proxy_provider,
        tcp_profile=arch.tcp_profile,
        tls_profile=arch.tls_profile,
        fingerprint=fingerprint,
        status=IdentityStatus.NEW,
        created_at=int(time.time()),
    )
