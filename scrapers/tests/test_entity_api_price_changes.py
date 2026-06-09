"""
entity-api /price-changes endpoint — the live PRICE-change surface (Bloque H).

Establishes test infra for services/entity_api (previously untested): a fake asyncpg pool
+ direct coroutine call (no uvicorn / httpx). Verifies entity-scoped price-change feed + 404.
"""
from __future__ import annotations

import asyncio
import datetime

import pytest

pytest.importorskip("fastapi")  # entity-api depends on fastapi; skip cleanly if absent
from services.entity_api import app as api  # noqa: E402


class _FakeConn:
    def __init__(self, entity, rows):
        self._e, self._rows = entity, rows

    async def fetchrow(self, sql, *a):   # _entity_or_404
        return self._e

    async def fetch(self, sql, *a):      # price-changes query
        return self._rows


class _FakePool:
    def __init__(self, entity, rows):
        self._e, self._rows = entity, rows

    def acquire(self):
        e, rows = self._e, self._rows

        class _Ctx:
            async def __aenter__(self_inner):
                return _FakeConn(e, rows)

            async def __aexit__(self_inner, *a):
                return False

        return _Ctx()


@pytest.mark.unit
def test_price_changes_returns_entity_scoped_events(monkeypatch):
    entity = {"entity_ulid": "se_x", "domain": "dacia-meaux.fr"}
    rows = [{
        "vin": "V1", "event_date": datetime.date(2026, 6, 9),
        "price_eur_prev": 18000.0, "price_eur_new": 17000.0,
        "price_delta_eur": -1000.0, "direction": "drop",
        "created_at": datetime.datetime(2026, 6, 9, 12, 0),
    }]
    monkeypatch.setattr(api, "_pool", _FakePool(entity, rows))
    res = asyncio.run(api.entity_price_changes("se_x", since=None, limit=50))
    assert res["success"] is True
    assert res["meta"]["count"] == 1
    assert res["meta"]["domain"] == "dacia-meaux.fr"
    assert res["data"][0]["direction"] == "drop"
    assert res["data"][0]["price_delta_eur"] == -1000.0


@pytest.mark.unit
def test_price_changes_404_when_entity_missing(monkeypatch):
    from fastapi import HTTPException

    class _NoEntPool(_FakePool):
        def acquire(self):
            class _Ctx:
                async def __aenter__(self_inner):
                    return _FakeConn(None, [])      # fetchrow -> None -> 404

                async def __aexit__(self_inner, *a):
                    return False
            return _Ctx()

    monkeypatch.setattr(api, "_pool", _NoEntPool(None, []))
    with pytest.raises(HTTPException) as ei:
        asyncio.run(api.entity_price_changes("missing", since=None, limit=50))
    assert ei.value.status_code == 404
