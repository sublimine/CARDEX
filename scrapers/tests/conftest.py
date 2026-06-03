"""Shared fixtures for the scraping-engine test suite."""
from __future__ import annotations

import sqlite3

import pytest

from scrapers import db
from scrapers.engine.identity import profile, store
from scrapers.engine.identity.profile import Identity, IdentityStatus, ProxyTier

# Fixed UUIDs keep the deterministic fingerprint RNG reproducible across runs.
_UUID_DE = "11111111-1111-1111-1111-111111111111"
_UUID_FR = "22222222-2222-2222-2222-222222222222"


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: fast, isolated unit test")
    config.addinivalue_line("markers", "integration: touches a real external resource")


@pytest.fixture
def conn() -> sqlite3.Connection:
    """An isolated, migrated in-memory engine.db."""
    c = db.connect(":memory:")
    db.migrate(c)
    yield c
    c.close()


@pytest.fixture
def make_identity():
    """Factory for coherent identities with a controllable id/country/ip."""

    def _make(
        country: str = "DE",
        proxy_ip: str = "203.0.113.7",
        identity_id: str = _UUID_DE,
        tier: ProxyTier = ProxyTier.ISP_STICKY,
    ) -> Identity:
        return profile.generate(country, proxy_ip, tier, identity_id=identity_id)

    return _make


@pytest.fixture
def active_identity(conn, make_identity) -> Identity:
    """A saved, warmed, active identity ready to be picked."""
    idy = make_identity()
    store.save(conn, idy)
    conn.execute(
        "UPDATE identities SET status=?, warming_done=1, trust_score=1.0 WHERE id=?",
        (IdentityStatus.ACTIVE.value, idy.id),
    )
    return store.get(conn, idy.id)
