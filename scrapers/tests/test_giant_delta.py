"""Diff-based SEEN/GONE delta for the platform giants (``run_giant_scraping``).

The giant harness persists rich rows to ``vehicles`` but historically never fired
``vehicle_events``, so the verifier's ``delta`` dimension failed for the giants (no SEEN).
``reconcile_events`` closes that gap with the canonical snapshot-diff: harvested URL set vs
the prior served set → INSERT SEEN for the new, INSERT GONE for the vanished. These tests pin
that contract without a live DB — a fake asyncpg connection records every statement and serves
a controllable prior-served set, so the diff math, the hash identity, and the gating are all
proven deterministically. The live PASS of ``dim_delta`` for autoscout24.de is the integration
proof; this is the unit spine.
"""
from __future__ import annotations

import asyncio

import pytest

from scrapers.common import indexer
from scripts import run_giant_scraping as g


def _run(coro):
    return asyncio.run(coro)


class _FakeConn:
    """Records executed SQL; answers the prior-served read from an injected fixture.

    ``events_live`` = rows the ledger read returns (latest-event-SEEN survivors). The ledger IS
    the snapshot store (no ``vehicles`` baseline), so this is the only read the reconcile makes.
    Every ``execute`` (the SEEN/GONE inserts) is appended to ``executed``.
    """

    def __init__(self, events_live: list[dict]):
        self._events_live = events_live
        self.executed: list[tuple[str, tuple]] = []

    async def fetch(self, sql: str, *args):
        if "FROM vehicle_events" in sql:
            return [dict(r) for r in self._events_live]
        raise AssertionError(f"unexpected fetch: {sql[:60]}")

    async def execute(self, sql: str, *args):
        self.executed.append((sql, args))
        return "OK"


class _FakePool:
    """``pool.acquire()`` async-context-manager yielding the same recording conn each time."""

    def __init__(self, conn: _FakeConn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Acq:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Acq()


def _inserts(conn: _FakeConn) -> dict[str, list[str]]:
    """Extract {SEEN: [urls...], GONE: [urls...]} actually inserted into vehicle_events."""
    out: dict[str, list[str]] = {"SEEN": [], "GONE": []}
    for sql, args in conn.executed:
        if "INSERT INTO vehicle_events" not in sql:
            continue
        etype = "SEEN" if "'SEEN'" in sql else "GONE" if "'GONE'" in sql else None
        if etype:
            # args = (hashes, urls, domain, cc); the URLs are arg index 1.
            out[etype].extend(args[1])
    return out


DOMAIN = "autoscout24.de"


@pytest.mark.unit
def test_complete_cycle_emits_seen_for_new_and_gone_for_vanished():
    # Prior served = {keep_url (in ledger), gone_url (in vehicles only)}.
    keep_url = f"https://www.{DOMAIN}/angebote/keep-1"
    gone_url = f"https://www.{DOMAIN}/angebote/gone-1"
    new_url = f"https://www.{DOMAIN}/angebote/new-1"
    keep_hash = indexer.url_hash(keep_url)

    # Ledger-live (prior snapshot) = {keep_url, gone_url}; harvest re-finds keep_url,
    # discovers new_url; gone_url has vanished.
    conn = _FakeConn(events_live=[
        {"url_hash": keep_hash, "url_original": keep_url},
        {"url_hash": indexer.url_hash(gone_url), "url_original": gone_url},
    ])
    res = _run(g.reconcile_events(_FakePool(conn), DOMAIN, "DE", {keep_url, new_url}))

    assert res == {"seen": 1, "gone": 1}
    ins = _inserts(conn)
    assert ins["SEEN"] == [new_url]            # only the genuinely-new URL → SEEN
    assert ins["GONE"] == [gone_url]           # only the vanished ledger-live URL → GONE
    assert keep_url not in ins["SEEN"] and keep_url not in ins["GONE"]  # zero-touch survivor


@pytest.mark.unit
def test_seen_hash_is_indexer_identity():
    """SEEN event carries the SAME url_hash the indexer/seal path uses (one identity)."""
    new_url = f"https://www.{DOMAIN}/angebote/identity-1"
    conn = _FakeConn(events_live=[])
    _run(g.reconcile_events(_FakePool(conn), DOMAIN, "DE", {new_url}))

    seen_inserts = [(sql, args) for sql, args in conn.executed
                    if "INSERT INTO vehicle_events" in sql and "'SEEN'" in sql]
    assert len(seen_inserts) == 1
    hashes, urls, dom, cc = seen_inserts[0][1]
    assert hashes == [indexer.url_hash(new_url)]
    assert urls == [new_url] and dom == DOMAIN and cc == "DE"


@pytest.mark.unit
def test_root_domain_urls_are_dropped():
    """``_hash_urls`` drops path-less URLs — a bare root never becomes a SEEN event."""
    conn = _FakeConn(events_live=[])
    res = _run(g.reconcile_events(
        _FakePool(conn), DOMAIN, "DE", {f"https://www.{DOMAIN}", f"https://www.{DOMAIN}/"}))
    assert res == {"seen": 0, "gone": 0}
    assert not any("INSERT INTO vehicle_events" in sql for sql, _ in conn.executed)


@pytest.mark.unit
def test_no_change_short_circuits_without_event_insert():
    """Harvest == prior served → no SEEN, no GONE, no event INSERT (idempotent re-run)."""
    url = f"https://www.{DOMAIN}/angebote/stable-1"
    conn = _FakeConn(events_live=[{"url_hash": indexer.url_hash(url), "url_original": url}])
    res = _run(g.reconcile_events(_FakePool(conn), DOMAIN, "DE", {url}))
    assert res == {"seen": 0, "gone": 0}
    assert not any("INSERT INTO vehicle_events" in sql for sql, _ in conn.executed)


@pytest.mark.unit
def test_first_complete_cycle_seeds_seen_for_all_harvested_and_no_gone():
    """Empty ledger (the giants' real starting state: 540k served rows, ZERO events): the first
    complete cycle SEEDs SEEN for every harvested URL and GONE for none — nothing has vanished
    against a prior snapshot that does not exist yet. This is what flips ``dim_delta`` to PASS."""
    u1 = f"https://www.{DOMAIN}/angebote/seed-1"
    u2 = f"https://www.{DOMAIN}/angebote/seed-2"
    conn = _FakeConn(events_live=[])
    res = _run(g.reconcile_events(_FakePool(conn), DOMAIN, "DE", {u1, u2}))

    assert res == {"seen": 2, "gone": 0}
    ins = _inserts(conn)
    assert sorted(ins["SEEN"]) == sorted([u1, u2])
    assert ins["GONE"] == []


@pytest.mark.unit
def test_second_cycle_gone_marks_vanished_ledger_url():
    """With a prior ledger snapshot, a complete harvest that drops a previously-live URL
    GONE-marks exactly that URL (sold/removed) — the true baja."""
    live_url = f"https://www.{DOMAIN}/angebote/was-live"
    conn = _FakeConn(events_live=[
        {"url_hash": indexer.url_hash(live_url), "url_original": live_url}])
    # Fresh harvest no longer contains live_url (it sold) and finds nothing new.
    res = _run(g.reconcile_events(_FakePool(conn), DOMAIN, "DE", set()))

    assert res == {"seen": 0, "gone": 1}
    assert _inserts(conn)["GONE"] == [live_url]


@pytest.mark.unit
def test_seen_inserts_are_chunked_at_pg_batch():
    """At giant scale a single unnest of a 540k-element text[] stalls PG for minutes, so SEEN/GONE
    inserts MUST be chunked at ``indexer._PG_BATCH`` (the lesson from the live autoscout24.de seed).
    ``_PG_BATCH + 1`` new URLs → exactly two INSERT statements, partitioning every URL once."""
    n = indexer._PG_BATCH + 1
    urls = {f"https://www.{DOMAIN}/angebote/bulk-{i}" for i in range(n)}
    conn = _FakeConn(events_live=[])
    res = _run(g.reconcile_events(_FakePool(conn), DOMAIN, "DE", urls))

    assert res == {"seen": n, "gone": 0}
    seen_stmts = [args for sql, args in conn.executed
                  if "INSERT INTO vehicle_events" in sql and "'SEEN'" in sql]
    assert len(seen_stmts) == 2                       # 500 + 1, not one 501-element mega-array
    assert [len(a[0]) for a in seen_stmts] == [indexer._PG_BATCH, 1]
    # Every harvested URL is emitted exactly once across the chunks (no drop, no dup).
    emitted = [u for a in seen_stmts for u in a[1]]
    assert sorted(emitted) == sorted(urls)


@pytest.mark.unit
def test_partial_slice_never_reconciles_in_harvest(monkeypatch):
    """The caller gate: with keep=False (partial slice), harvest must NOT call reconcile_events
    (a partial set would GONE-mark live listings it never reached)."""
    called = {"n": 0}

    async def _spy(*a, **k):  # pragma: no cover - asserted not reached
        called["n"] += 1
        return {"seen": 0, "gone": 0}

    monkeypatch.setattr(g, "reconcile_events", _spy)

    # Drive harvest with everything stubbed so only the keep-gate logic is exercised.
    async def _drive():
        async def fake_count(lo, hi):
            return 0  # no segments planned → loop body is a no-op, fast

        # Patch the network + DB seams the harvest touches.
        monkeypatch.setattr(g, "make_dealer_fetcher", lambda: (lambda *a, **k: None))

        class _Pool:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *e):
                return False

            def acquire(self):
                return self

            async def fetchval(self, *a, **k):
                return 0

            async def execute(self, *a, **k):
                return "OK"

            async def close(self):
                return None

        async def fake_create_pool(*a, **k):
            return _Pool()

        monkeypatch.setattr(g.asyncpg, "create_pool", fake_create_pool)

        async def fake_safe_fetch(*a, **k):
            return None

        monkeypatch.setattr(g, "_safe_fetch", fake_safe_fetch)
        # base_total count_fn uses _safe_fetch→None→0, so 0 segments; persist loop never runs.
        await g.harvest(DOMAIN, "DE", base=f"https://www.{DOMAIN}", currency="EUR",
                        limit=0, cap=4000, max_price=1000, keep=False, passes=1)

    _run(_drive())
    assert called["n"] == 0  # partial slice → reconcile never invoked
