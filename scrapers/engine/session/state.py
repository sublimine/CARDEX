"""
Session state — persistencia de storageState (cookies + localStorage) por identidad+dominio.

Playwright storageState es un JSON con cookies[] + origins[].
Se persiste en engine.db tabla identities.storage_state (BLOB).
Se carga en el browser context antes de cada sesión.
Se guarda tras cada sesión exitosa — acumula historial real.

Conexión con sensor.py: _abck se extrae del storageState post-sesión y se persiste
  separadamente en identities.abck_tokens para refresh sin browser completo.

Formato del BLOB: este módulo es el ÚNICO dueño del contenido de
identities.storage_state. La columna guarda un mapa JSON {domain: storageState}
codificado UTF-8 — un storageState aislado por dominio (los origins de localStorage
son por-origen, así que no se pueden fusionar entre dominios). store.py trata la
columna como bytes opacos; nadie más la parsea.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any


def _load_map(conn: sqlite3.Connection, identity_id: str) -> dict[str, dict]:
    """Read the whole {domain: storageState} map for an identity ({} if none)."""
    row = conn.execute(
        "SELECT storage_state FROM identities WHERE id = ?", (identity_id,)
    ).fetchone()
    if row is None:
        return {}
    blob = row["storage_state"]
    if not blob:
        return {}
    try:
        data = json.loads(blob)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load(conn: sqlite3.Connection, identity_id: str, domain: str) -> dict | None:
    """Load Playwright storageState for (identity, domain). None if first visit."""
    return _load_map(conn, identity_id).get(domain)


def save(conn: sqlite3.Connection, identity_id: str, domain: str, state: dict) -> None:
    """Persist storageState after successful session. Overwrites previous for domain."""
    by_domain = _load_map(conn, identity_id)
    by_domain[domain] = state
    conn.execute(
        "UPDATE identities SET storage_state = ? WHERE id = ?",
        (json.dumps(by_domain).encode("utf-8"), identity_id),
    )


def extract_abck(storage_state: dict, domain: str) -> str | None:
    """Extract _abck cookie value from storageState for the given domain."""
    for cookie in storage_state.get("cookies", []):
        if cookie.get("name") == "_abck" and domain in cookie.get("domain", ""):
            return cookie.get("value")
    return None


def _localstorage_script(origin: str, items: list[dict]) -> str:
    """
    Build an init script that seeds localStorage for `origin` only.

    Playwright/Camoufox have no post-creation storageState setter, so localStorage
    is restored via add_init_script: the script runs in every document and writes
    the entries when the page's origin matches. Values are JSON-embedded so quotes
    and unicode survive intact.
    """
    payload = json.dumps(items)
    target = json.dumps(origin)
    return (
        "(() => {"
        f"  if (window.location.origin !== {target}) return;"
        f"  const items = {payload};"
        "  for (const it of items) {"
        "    try { window.localStorage.setItem(it.name, it.value); } catch (e) {}"
        "  }"
        "})();"
    )


async def inject_into_context(context: Any, storage_state: dict) -> None:
    """
    Apply storageState to an existing Playwright/Camoufox browser context.
    Must be called before page.goto() to ensure cookies are present from request 1.

    Cookies go through context.add_cookies (immediate). localStorage origins are
    replayed via add_init_script (deferred to first navigation per origin).
    """
    cookies = storage_state.get("cookies")
    if cookies:
        await context.add_cookies(cookies)
    for origin in storage_state.get("origins", []):
        items = origin.get("localStorage") or []
        if not items:
            continue
        await context.add_init_script(_localstorage_script(origin.get("origin", ""), items))
