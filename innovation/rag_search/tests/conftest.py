"""Shared pytest fixtures for CARDEX RAG tests."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure the rag_search package is importable from tests/
RAG_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(RAG_ROOT))

FIXTURES_PATH = Path(__file__).parent / "fixtures.json"


@pytest.fixture(scope="session")
def fixtures() -> list[dict]:
    return json.loads(FIXTURES_PATH.read_text())


@pytest.fixture()
def rag_db(tmp_path: Path, fixtures: list[dict]) -> Path:
    """Temporary SQLite database populated with test fixtures."""
    db_path = tmp_path / "test_discovery.db"
    con = sqlite3.connect(str(db_path))
    con.executescript("""
        CREATE TABLE IF NOT EXISTS dealer_entity (
            dealer_id    TEXT PRIMARY KEY,
            country_code TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS vehicle_record (
            vehicle_id       TEXT PRIMARY KEY,
            dealer_id        TEXT NOT NULL,
            make_canonical   TEXT,
            model_canonical  TEXT,
            year             INTEGER,
            mileage_km       INTEGER,
            fuel_type        TEXT,
            transmission     TEXT,
            body_type        TEXT,
            color            TEXT,
            power_kw         INTEGER,
            price_gross_eur  REAL,
            confidence_score REAL DEFAULT 0.8,
            source_url       TEXT DEFAULT '',
            source_platform  TEXT DEFAULT 'test',
            status           TEXT DEFAULT 'ACTIVE',
            indexed_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    for f in fixtures:
        dealer_id = "dealer_" + f["vehicle_id"]
        con.execute(
            "INSERT OR IGNORE INTO dealer_entity (dealer_id, country_code) VALUES (?, ?)",
            (dealer_id, f["country"]),
        )
        con.execute(
            """INSERT OR REPLACE INTO vehicle_record
               (vehicle_id, dealer_id, make_canonical, model_canonical, year,
                mileage_km, fuel_type, transmission, body_type, color, power_kw,
                price_gross_eur)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                f["vehicle_id"],
                dealer_id,
                f["make"],
                f["model"],
                f["year"],
                f["mileage_km"],
                f["fuel_type"],
                f["transmission"],
                f["body_type"],
                f["color"],
                f["power_kw"],
                f["price_eur"],
            ),
        )
    con.commit()
    con.close()
    return db_path


@pytest.fixture()
def rag_data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "rag"
    d.mkdir()
    return d
