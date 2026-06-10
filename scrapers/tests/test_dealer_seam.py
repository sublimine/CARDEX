"""Dealer seam wiring tests — ``make_live_seam`` contract against A6/A7 doubles.

The consolidation invariant under test: the dealer cage path MUST run A7 with
``entity_kind='dealer'`` so every caged vehicle registers its ``source_entities``
row and carries ``entity_ulid`` (otherwise the per-entity inventory API cannot
serve the dealer's inventory). No network, Redis, or Postgres in the hot path.
"""
from __future__ import annotations

import asyncio

import pytest

from scrapers.dealer_scraping import seam


def _run(coro):
    return asyncio.run(coro)


class FakeRedis:
    def __init__(self):
        self.deleted: list[str] = []
        self.added: list[tuple[str, dict]] = []

    async def delete(self, stream):
        self.deleted.append(stream)

    async def xadd(self, stream, fields):
        self.added.append((stream, fields))


class _Stats:
    def __init__(self, persisted: int):
        self.persisted = persisted


@pytest.mark.unit
def test_make_live_seam_runs_a7_with_dealer_entity_kind(monkeypatch):
    a6_calls, a7_calls = [], []

    async def fake_a6_run(**kw):
        a6_calls.append(kw)

    async def fake_a7_run(**kw):
        a7_calls.append(kw)
        return _Stats(persisted=3)

    monkeypatch.setattr(seam.a6, "run", fake_a6_run)
    monkeypatch.setattr(seam.a7, "run", fake_a7_run)

    rdb = FakeRedis()
    runner = seam.make_live_seam(
        rdb, static_fetcher=None, e07_fetcher=None,
        redis_url="redis://throwaway:56390", db_url="postgres://x/cardex", isolate=True,
    )
    urls = ["https://pouwtest.nl/occasions/audi-1", "https://pouwtest.nl/occasions/vw-2"]
    persisted = _run(runner("pouwtest.nl", "NL", urls, False))

    assert persisted == 3
    assert len(a6_calls) == 1 and len(a7_calls) == 1
    # THE invariant: the dealer cage path links entities (kind='dealer') in A7.
    assert a7_calls[0]["entity_kind"] == "dealer"
    assert a7_calls[0]["database_url"] == "postgres://x/cardex"
    assert a7_calls[0]["limit"] == len(urls) and a7_calls[0]["batch_size"] == len(urls)
    # isolate=True wiped both streams before seeding the enrich queue.
    assert set(rdb.deleted) == {seam.a6.ENRICH_STREAM, seam.a6.INGESTION_STREAM}
    assert [s for s, _ in rdb.added] == [seam.a6.ENRICH_STREAM] * len(urls)


@pytest.mark.unit
def test_make_live_seam_empty_urls_short_circuits(monkeypatch):
    async def boom(**kw):  # pragma: no cover - must never be reached
        raise AssertionError("A6/A7 must not run for an empty url list")

    monkeypatch.setattr(seam.a6, "run", boom)
    monkeypatch.setattr(seam.a7, "run", boom)

    rdb = FakeRedis()
    runner = seam.make_live_seam(
        rdb, static_fetcher=None, e07_fetcher=None,
        redis_url="redis://throwaway:56390", db_url="postgres://x/cardex",
    )
    assert _run(runner("pouwtest.nl", "NL", [], False)) == 0
    assert rdb.deleted == [] and rdb.added == []
