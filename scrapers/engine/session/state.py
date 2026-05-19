"""
Session state — persistencia de storageState (cookies + localStorage) por identidad+dominio.

Playwright storageState es un JSON con cookies[] + origins[].
Se persiste en engine.db tabla identities.storage_state (BLOB).
Se carga en el browser context antes de cada sesión.
Se guarda tras cada sesión exitosa — acumula historial real.

Conexión con sensor.py: _abck se extrae del storageState post-sesión y se persiste
  separadamente en identities.abck_tokens para refresh sin browser completo.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any


def load(conn: sqlite3.Connection, identity_id: str, domain: str) -> dict | None:
    """Load Playwright storageState for (identity, domain). None if first visit."""
    raise NotImplementedError


def save(conn: sqlite3.Connection, identity_id: str, domain: str, state: dict) -> None:
    """Persist storageState after successful session. Overwrites previous."""
    raise NotImplementedError


def extract_abck(storage_state: dict, domain: str) -> str | None:
    """Extract _abck cookie value from storageState for the given domain."""
    for cookie in storage_state.get("cookies", []):
        if cookie.get("name") == "_abck" and domain in cookie.get("domain", ""):
            return cookie.get("value")
    return None


def inject_into_context(context, storage_state: dict) -> None:
    """
    Apply storageState to an existing Playwright/Camoufox browser context.
    Must be called before page.goto() to ensure cookies are present from request 1.
    """
    raise NotImplementedError
