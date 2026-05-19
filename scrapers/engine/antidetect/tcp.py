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

from scrapers.engine.identity.profile import Identity, TCPProfile

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


def is_available() -> bool:
    """Check if httpcloak binary and npcap/libpcap are present."""
    raise NotImplementedError


def apply_profile(identity: Identity) -> None:
    """
    Configure httpcloak to use identity.tcp_profile for subsequent requests.
    No-op if is_available() is False (degraded mode — log warning once).
    """
    raise NotImplementedError
