"""
TCP fingerprint — httpcloak para spoofing del TCP SYN packet.

Anula la detección de OS a nivel de red (p0f, Cloudflare Network Analytics).
Sin esto: user_agent dice Windows 11 pero el TCP stack delata Linux/Docker.

Requiere: npcap (Windows) o libpcap (Linux) + CAP_NET_RAW.
Binario: httpcloak (Go) — wraps curl_cffi sessions con TCP profile correcto.

Profiles (deben coincidir con identity.tcp_profile):
  windows_11:  TTL=128, Window=65535, options=[MSS, NOP, WS=8, NOP, SACK]
  macos_14:    TTL=64,  Window=65535, options=[MSS, NOP, WS=6, SACK, TS, NOP, NOP]
  ubuntu_22:   TTL=64,  Window=29200, options=[MSS, SACK, TS, NOP, WS=7]

Invariante: tcp_profile DEBE ser coherente con user_agent OS.
  Chrome + Windows UA → windows_11. Firefox + macOS UA → macos_14.
  Enforced en coherence.py.

Nota: si httpcloak/npcap no disponible → continuar sin TCP spoofing.
  Impacto: CF Network Analytics puede detectar OS mismatch en Tier 2+.
  Aceptable en MVP — implementar antes de escalar T2 a producción.
"""
from __future__ import annotations

import ctypes.util
import logging
import os
import shutil
import sys

from scrapers.engine.identity.profile import Identity, TCPProfile

log = logging.getLogger(__name__)

# httpcloak binary — overridable so an out-of-band install can be pointed at.
_HTTPCLOAK_BIN = os.environ.get("HTTPCLOAK_BIN", "httpcloak")

# Latch so the degraded-mode warning is emitted exactly once per process.
_degraded_warned = False

_PROFILES: dict[TCPProfile, dict] = {
    TCPProfile.WINDOWS_11: {
        "ttl": 128,
        "window": 65535,
        "options": ["MSS", "NOP", "WS=8", "NOP", "SACK"],
    },
    TCPProfile.MACOS_14: {
        "ttl": 64,
        "window": 65535,
        "options": ["MSS", "NOP", "WS=6", "SACK", "TS", "NOP", "NOP"],
    },
    TCPProfile.UBUNTU_22: {
        "ttl": 64,
        "window": 29200,
        "options": ["MSS", "SACK", "TS", "NOP", "WS=7"],
    },
}


# npcap installs wpcap.dll into System32 (or SysWOW64 for 32-bit). libpcap on
# POSIX is resolved through the dynamic linker via ctypes.util.find_library.
_WIN_PCAP_DLLS = (
    r"C:\Windows\System32\Npcap\wpcap.dll",
    r"C:\Windows\System32\wpcap.dll",
    r"C:\Windows\SysWOW64\Npcap\wpcap.dll",
)


def _pcap_present() -> bool:
    """True if a packet-capture library (libpcap/npcap) can be located."""
    if ctypes.util.find_library("pcap"):
        return True
    if sys.platform == "win32":
        return any(os.path.exists(p) for p in _WIN_PCAP_DLLS)
    return False


def is_available() -> bool:
    """Check if httpcloak binary and npcap/libpcap are present."""
    return shutil.which(_HTTPCLOAK_BIN) is not None and _pcap_present()


def apply_profile(identity: Identity) -> None:
    """
    Configure httpcloak to use identity.tcp_profile for subsequent requests.
    No-op if is_available() is False (degraded mode — log warning once).

    The httpcloak invocation contract is provider-specific and not wired in-repo.
    We resolve the profile (validating the identity carries a known TCPProfile)
    and, until that contract is configured, log selection at debug level. We never
    fabricate a CLI contract just to appear to "succeed" — see module docstring.
    """
    global _degraded_warned
    profile = _PROFILES[identity.tcp_profile]

    if not is_available():
        if not _degraded_warned:
            log.warning(
                "httpcloak/pcap unavailable (set HTTPCLOAK_BIN, install npcap/"
                "libpcap) — TCP SYN spoofing disabled, running in degraded mode. "
                "CF Network Analytics may detect OS mismatch in Tier 2+."
            )
            _degraded_warned = True
        return

    log.debug(
        "httpcloak TCP profile selected for identity=%s: %s ttl=%d window=%d",
        identity.id, identity.tcp_profile.value, profile["ttl"], profile["window"],
    )
