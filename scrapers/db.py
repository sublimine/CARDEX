"""
engine.db — SQLite WAL factory.

Single source of truth for all scraping state:
  identities, proxy health, domain tier state, work queue, DLQ, schema registry, warming schedule.

Schema defined in SCRAPING_ENGINE.md § DATA MODEL.
WAL mode: concurrent readers never block the writer.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

_DEFAULT_PATH = Path(__file__).parent / "engine.db"


def connect(path: Path | str = _DEFAULT_PATH) -> sqlite3.Connection:
    """Return a WAL-mode connection. Thread-local — do not share across threads."""
    raise NotImplementedError


def migrate(conn: sqlite3.Connection) -> None:
    """Apply all DDL migrations idempotently. Safe to call on every startup."""
    raise NotImplementedError
