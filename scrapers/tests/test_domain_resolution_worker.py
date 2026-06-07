"""
Domain-resolution worker — the concurrency-sensitive queue layer.

Two things had no coverage and are the riskiest part of the worker:
  * collision-merge: when a validated domain already belongs to another (domain,country)
    row, ``_resolve_one`` must catch the unique violation and merge instead of crashing
    or fabricating. Tested with a fake pool + fully-faked session (no network, no PG).
  * ``FOR UPDATE SKIP LOCKED`` claim: two workers claiming concurrently must get DISJOINT
    rows and never double-claim. Tested against a real Postgres on an ISOLATED throwaway
    table (never ``discovery_candidates`` — another session owns that), auto-dropped.
"""
from __future__ import annotations

import asyncio
import os
import urllib.parse

import asyncpg
import pytest

from scrapers.discovery.domain_resolution import worker as W

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")

# A dealer homepage that validates for "Autohaus Hable" (whole-word name + strong auto).
_DEALER_HOME = (
    "<html><head><title>Autohaus Hable</title></head><body>"
    "<h1>Willkommen bei Autohaus Hable in Grafenau</h1>"
    "<p>Neuwagen, Gebrauchtwagen und Fahrzeuge. Werkstatt und Probefahrt.</p>"
    + ("<p>lorem ipsum dolor sit amet consectetur adipiscing elit. </p>" * 8)
    + "</body></html>"
)


def _ddg_results_for(host: str) -> str:
    uddg = urllib.parse.quote(f"https://{host}/", safe="")
    pad = "<div class='r'>noise</div>" * 80           # exceed the worker's len>1000 floor
    return f'<html><body>{pad}<a class="result__a" href="//duckduckgo.com/l/?uddg={uddg}">Hable</a></body></html>'


class _FakeResp:
    def __init__(self, status: int, text: str):
        self.status_code = status
        self.text = text


class _FakeSession:
    """Routes by URL substring; accepts the worker's get(**kwargs) (incl. verify=False)."""

    def __init__(self, home_host: str, home_html: str):
        self._home_host = home_host
        self._home_html = home_html
        self.requested: list[str] = []

    async def get(self, url: str, **kw):
        self.requested.append(url)
        if "gelbeseiten" in url or "pagesjaunes" in url or "local.ch" in url:
            return _FakeResp(200, "")                  # directory finds nothing → no candidate
        if "duckduckgo" in url or "mojeek" in url:
            return _FakeResp(200, _ddg_results_for(self._home_host))
        if self._home_host in url:
            return _FakeResp(200, self._home_html)
        return _FakeResp(404, "")


class _FakePool:
    """Records executes; optionally fails the PROMOTE with a unique violation."""

    def __init__(self, fail_promote: bool):
        self.fail_promote = fail_promote
        self.executed: list[str] = []

    async def execute(self, sql: str, *args):
        self.executed.append(sql)
        if self.fail_promote and "sitemap_status = 'pending'" in sql:
            raise asyncpg.UniqueViolationError("dup (domain,country)")
        return "UPDATE 1"


def _row():
    return {"id": 1, "name": "Autohaus Hable", "city": "Grafenau", "country": "DE", "email": None}


# ── collision-merge (no PG, no network) ──────────────────────────────────────────
@pytest.mark.unit
def test_resolve_one_promotes_when_domain_free():
    pool = _FakePool(fail_promote=False)
    sess = _FakeSession("hable.de", _DEALER_HOME)
    stats = W.Stats()
    asyncio.run(W._resolve_one(pool, sess, _row(), stats))
    assert stats.resolved == 1 and stats.collided == 0 and stats.failed == 0
    assert any("sitemap_status = 'pending'" in s for s in pool.executed)   # PROMOTE ran


@pytest.mark.unit
def test_resolve_one_collision_merges_not_crashes():
    pool = _FakePool(fail_promote=True)                 # domain already owned by another row
    sess = _FakeSession("hable.de", _DEALER_HOME)
    stats = W.Stats()
    asyncio.run(W._resolve_one(pool, sess, _row(), stats))
    assert stats.collided == 1 and stats.resolved == 0 and stats.failed == 0
    assert any("DELETE FROM discovery_candidates" in s for s in pool.executed)  # COLLISION_MERGE ran


@pytest.mark.unit
def test_resolve_one_marks_fail_with_granular_reason_when_no_candidate():
    pool = _FakePool(fail_promote=False)
    sess = _FakeSession("hable.de", "<html><body>nothing</body></html>")  # home won't validate
    # search returns hable.de but its homepage no longer validates → candidates_rejected
    stats = W.Stats()
    asyncio.run(W._resolve_one(pool, sess, _row(), stats))
    assert stats.failed == 1 and stats.resolved == 0
    assert any("ddg_attempts = ddg_attempts + 1" in s for s in pool.executed)   # MARK_FAIL ran


# ── FOR UPDATE SKIP LOCKED claim (real PG, isolated throwaway table) ──────────────
@pytest.mark.integration
def test_skip_locked_claim_is_disjoint_under_concurrency():
    async def go():
        try:
            pool = await asyncpg.create_pool(_DSN, min_size=4, max_size=10)
        except Exception:  # noqa: BLE001
            pytest.skip("postgres not available")
        tbl = "_p2_claim_probe"
        claim = (
            f"WITH c AS (SELECT id FROM {tbl} WHERE claimed_by IS NULL "
            f"ORDER BY id LIMIT $2 FOR UPDATE SKIP LOCKED) "
            f"UPDATE {tbl} t SET claimed_by=$1 FROM c WHERE t.id=c.id RETURNING t.id"
        )
        try:
            await pool.execute(f"DROP TABLE IF EXISTS {tbl}")
            await pool.execute(f"CREATE TABLE {tbl} (id bigserial PRIMARY KEY, claimed_by text)")
            await pool.execute(f"INSERT INTO {tbl} (claimed_by) SELECT NULL FROM generate_series(1,60)")

            async def claimer(name: str) -> list[int]:
                got: list[int] = []
                while True:
                    rows = await pool.fetch(claim, name, 7)
                    if not rows:
                        return got
                    got.extend(r["id"] for r in rows)
                    await asyncio.sleep(0)              # yield so workers interleave

            a, b, c = await asyncio.gather(claimer("A"), claimer("B"), claimer("C"))
            assert sorted(a + b + c) == list(range(1, 61))     # every row claimed exactly once
            assert set(a).isdisjoint(b) and set(a).isdisjoint(c) and set(b).isdisjoint(c)
        finally:
            await pool.execute(f"DROP TABLE IF EXISTS {tbl}")
            await pool.close()

    asyncio.run(go())
