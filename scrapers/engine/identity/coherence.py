"""
Coherence enforcer — garantiza que todos los campos de una identidad son mutuamente coherentes.

Comprobaciones en CREACIÓN:
  - tcp_profile coherente con user_agent OS (Chrome/Windows → windows_11)
  - tls_profile coherente con user_agent browser (Chrome → chrome136)
  - timezone coherente con país asignado
  - locale coherente con país asignado
  - webrtc_ip en el mismo país que proxy_ip

Comprobaciones antes de CADA SESIÓN:
  - proxy_ip sigue activo (health check)
  - webrtc_ip sigue coherente con proxy_ip actual
  - _abck token del dominio no expirado (<1h restante → refresh)
  - storage_state no corrupto

Cualquier incoherencia → raise CoherenceError. Sesión NO iniciada.
"""
from __future__ import annotations

from scrapers.engine.identity.profile import Identity


class CoherenceError(ValueError):
    """Identity has incoherent fields. Do not use for scraping."""


_COUNTRY_TIMEZONES: dict[str, str] = {
    "DE": "Europe/Berlin",
    "ES": "Europe/Madrid",
    "FR": "Europe/Paris",
    "NL": "Europe/Amsterdam",
    "BE": "Europe/Brussels",
    "CH": "Europe/Zurich",
}

_COUNTRY_LOCALES: dict[str, str] = {
    "DE": "de-DE",
    "ES": "es-ES",
    "FR": "fr-FR",
    "NL": "nl-NL",
    "BE": "fr-BE",
    "CH": "de-CH",
}


def validate_creation(identity: Identity) -> None:
    """Raise CoherenceError if identity fields are incoherent at creation time."""
    raise NotImplementedError


def validate_pre_session(identity: Identity, domain: str) -> None:
    """Raise CoherenceError if identity is not safe to use for this domain right now."""
    raise NotImplementedError
