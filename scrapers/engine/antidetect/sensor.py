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

import json
import logging
import os
import shutil
import sqlite3
import time

log = logging.getLogger(__name__)

# hyper-sdk-go binary — name overridable so an out-of-band install can be pointed
# at without code change. Located via PATH (shutil.which).
_HYPER_SDK_BIN = os.environ.get("HYPER_SDK_GO_BIN", "hyper-sdk-go")


def _read_tokens(conn: sqlite3.Connection, identity_id: str) -> dict | None:
    """Return the parsed abck_tokens map, or None if the identity row is absent."""
    row = conn.execute(
        "SELECT abck_tokens FROM identities WHERE id = ?", (identity_id,)
    ).fetchone()
    if row is None:
        return None
    raw = row["abck_tokens"]
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def get_token(conn: sqlite3.Connection, identity_id: str, domain: str) -> dict | None:
    """Return valid _abck token for (identity, domain) or None if absent/expired."""
    tokens = _read_tokens(conn, identity_id)
    if not tokens:
        return None
    token = tokens.get(domain)
    if token is None:
        return None
    if token.get("expires", 0) <= time.time():
        return None
    return token


def store_token(
    conn: sqlite3.Connection,
    identity_id: str,
    domain: str,
    token: str,
    expires: int,
    trust_level: int = 1,
) -> None:
    """
    Persist a freshly generated _abck for (identity, domain).

    request_count resets to 0: a stored token is a new token, and needs_refresh
    counts requests made against THIS token. Other domains' tokens are preserved.
    """
    tokens = _read_tokens(conn, identity_id)
    if tokens is None:
        return  # unknown identity — store.save owns row creation
    tokens[domain] = {
        "token": token,
        "expires": int(expires),
        "trust_level": trust_level,
        "request_count": 0,
    }
    conn.execute(
        "UPDATE identities SET abck_tokens = ? WHERE id = ?",
        (json.dumps(tokens), identity_id),
    )


def hyper_sdk_path() -> str | None:
    """Absolute path to the hyper-sdk-go binary if installed, else None."""
    return shutil.which(_HYPER_SDK_BIN)


async def refresh_token(identity_id: str, domain: str, proxy_url: str) -> str | None:
    """
    Refresh _abck using hyper-sdk-go without a full browser.
    hyper-sdk-go is a Go binary that speaks the Akamai sensor protocol.
    Returns new token or None if refresh failed (triggers Fase 2 warming).

    Degraded mode: the binary's invocation contract is provider-specific and not
    wired in-repo. We detect availability and, until that contract is configured,
    signal refresh-unavailable (None) so the caller falls back to Fase 2 warming —
    the documented fallback — rather than proceeding on a stale/invalid token. We
    never fabricate a CLI contract just to appear to "succeed".
    """
    binary = hyper_sdk_path()
    if binary is None:
        log.warning(
            "hyper-sdk-go not found (set HYPER_SDK_GO_BIN); cannot refresh _abck "
            "for %s/%s — falling back to Fase 2 warming",
            identity_id, domain,
        )
        return None
    log.warning(
        "hyper-sdk-go present at %s but its invocation contract is not configured; "
        "returning None so %s/%s falls back to Fase 2 warming",
        binary, identity_id, domain,
    )
    return None


def needs_refresh(token: dict) -> bool:
    """True if token expires in < 3600s or request_count > 500."""
    return (token.get("expires", 0) - time.time() < 3600) or (token.get("request_count", 0) > 500)
