"""
Akamai sensor — _abck token store + refresh sin browser completo.

_abck es el token de sesión de Akamai Bot Manager v3.
  - Generado por sensor.js al visitar el portal (FASE 2 del warming)
  - Válido ~4h para uso activo (extend automáticamente con requests)
  - Refresco: hyper-sdk-go puede regenerarlo sin necesidad de browser completo

Tokens almacenados en engine.db tabla identities.abck_tokens (JSON):
  {"autoscout24.de": {"token": "...", "expires": int, "trust_level": int, "request_count": int}}

Invariante: ninguna request a portal Akamai sin _abck válido.
  Si token ausente → Fase 2 warming antes de cualquier extracción.
  Si token expirado → refresh con hyper-sdk-go. Si falla → Fase 2 warming.
"""
from __future__ import annotations

import sqlite3
import time


def get_token(conn: sqlite3.Connection, identity_id: str, domain: str) -> dict | None:
    """Return valid _abck token for (identity, domain) or None if absent/expired."""
    raise NotImplementedError


def store_token(
    conn: sqlite3.Connection,
    identity_id: str,
    domain: str,
    token: str,
    expires: int,
    trust_level: int = 1,
) -> None:
    raise NotImplementedError


async def refresh_token(identity_id: str, domain: str, proxy_url: str) -> str | None:
    """
    Refresh _abck using hyper-sdk-go without a full browser.
    hyper-sdk-go is a Go binary that speaks the Akamai sensor protocol.
    Returns new token or None if refresh failed (triggers Fase 2 warming).
    """
    raise NotImplementedError


def needs_refresh(token: dict) -> bool:
    """True if token expires in < 3600s or request_count > 500."""
    return (token.get("expires", 0) - time.time() < 3600) or (token.get("request_count", 0) > 500)
