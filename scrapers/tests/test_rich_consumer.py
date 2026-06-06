"""
A7 rich_consumer tests — pure persistence logic, no live PG/Redis.

Coverage:
  * compute_fingerprint  VIN-priority vs URL-based, deterministic
  * validate_payload     ok + every reject reason (make/model/year/url)
  * resolve_source_id    source_id → source_listing_id → url-hash (H1 guard)
  * build_insert_args    ordering, FX (EUR identity), Decimal numerics, photos
  * process_message      routing against in-memory PG/Redis doubles
"""
from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import pytest

from scrapers import rich_consumer as rc
from scrapers.rich_consumer import (
    RichStats,
    build_insert_args,
    compute_fingerprint,
    resolve_source_id,
    validate_payload,
)


def _run(coro):
    return asyncio.run(coro)


def _payload(**over) -> dict:
    base = {
        "make": "Audi", "model": "A4", "year": 2018,
        "source_url": "https://gaspedaal.nl/audi/a4/123",
        "source_listing_id": "URLHASH",
        "price_raw": 18500.0, "currency_raw": "EUR",
        "mileage_km": 90000, "color": "grey", "vin": "",
        "photo_urls": ["https://cdn/1.jpg"], "source_country": "NL",
    }
    base.update(over)
    return base


# ── compute_fingerprint ─────────────────────────────────────────────────────────
@pytest.mark.unit
def test_fingerprint_vin_priority_deterministic():
    fp1 = compute_fingerprint("WAUZZZ8E56A123456", "https://x/1", "black", 1000)
    fp2 = compute_fingerprint("WAUZZZ8E56A123456", "https://different/2", "black", 1000)
    assert fp1 == fp2  # VIN dominates → URL irrelevant
    assert len(fp1) == 64


@pytest.mark.unit
def test_fingerprint_url_based_when_no_vin():
    fp = compute_fingerprint("", "https://x.nl/a/1", "red", 5000)
    assert fp == compute_fingerprint("", "https://x.nl/a/1", "ignored", 9999)  # url only


# ── validate_payload ─────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_validate_ok():
    assert validate_payload(_payload()) is None


@pytest.mark.unit
@pytest.mark.parametrize("over,expected", [
    ({"make": ""}, "missing_make_model"),
    ({"model": ""}, "missing_make_model"),
    ({"year": 1900}, "unrealistic_year"),
    ({"year": 2099}, "unrealistic_year"),
    ({"source_url": ""}, "no_source_url"),
    ({"source_url": "https://gaspedaal.nl/"}, "root_domain_url"),
])
def test_validate_rejects(over, expected):
    assert validate_payload(_payload(**over)) == expected


# ── resolve_source_id (H1) ───────────────────────────────────────────────────────
@pytest.mark.unit
def test_resolve_source_id_prefers_explicit():
    assert resolve_source_id({"source_id": "SID", "source_listing_id": "LID"}) == "SID"


@pytest.mark.unit
def test_resolve_source_id_falls_back_to_listing_id():
    assert resolve_source_id({"source_id": "", "source_listing_id": "LID"}) == "LID"


@pytest.mark.unit
def test_resolve_source_id_final_guard_hashes_url():
    sid = resolve_source_id({"source_url": "https://x.nl/a/1"})
    assert sid and len(sid) == 32  # never empty → NOT NULL satisfied


# ── build_insert_args ────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_build_insert_args_eur_and_ordering():
    args, eur, fp = build_insert_args(
        _payload(), source="gaspedaal.nl", channel="SCRAPER", rates={"EUR": Decimal(1)},
    )
    assert len(args) == 30
    assert len(args[0]) == 26          # $1 vehicle_ulid (ULID)
    assert args[1] == fp               # $2 fingerprint
    assert args[3] == "URLHASH"        # $4 source_id (from listing id; H1)
    assert args[4] == "gaspedaal.nl"   # $5 source_platform
    assert args[6] == "https://gaspedaal.nl/audi/a4/123"  # $7 source_url
    assert args[8] == ["https://cdn/1.jpg"]               # $9 photo_urls
    assert args[10] == "Audi" and args[11] == "A4"        # make/model
    assert args[13] == 2018                                # year (int)
    assert args[20] == Decimal("18500")                    # $21 price_raw (numeric)
    assert args[22] == Decimal("18500")                    # $23 eur (EUR identity)
    assert eur == Decimal("18500")


@pytest.mark.unit
def test_build_insert_args_unknown_fx_leaves_eur_none():
    args, eur, _ = build_insert_args(
        _payload(currency_raw="CHF", price_raw=20000.0),
        source="autolina.ch", channel="SCRAPER", rates={"EUR": Decimal(1)},
    )
    assert eur is None
    assert args[22] is None            # stored with NULL EUR, not dropped


@pytest.mark.unit
def test_ch_listing_without_currency_defaults_to_chf_not_eur():
    # The 41.8% fix: a CH payload whose parser yielded no currency must NOT fall to
    # the EUR table-default — it defaults to CHF, and converts when FX_RATE_CHF is set.
    args, eur, _ = build_insert_args(
        _payload(source_country="CH", currency_raw="", price_raw=20000.0),
        source="autolina.ch", channel="SCRAPER",
        rates={"EUR": Decimal(1), "CHF": Decimal("1.05")},
    )
    assert args[21] == "CHF"                       # $22 currency_raw → country default
    assert eur == Decimal("21000.00")              # 20000 CHF * 1.05


@pytest.mark.unit
def test_nl_listing_without_currency_defaults_to_eur():
    args, eur, _ = build_insert_args(
        _payload(source_country="NL", currency_raw="", price_raw=15000.0),
        source="autotrack.nl", channel="SCRAPER", rates={"EUR": Decimal(1)},
    )
    assert args[21] == "EUR"
    assert eur == Decimal("15000")


# ── process_message routing (in-memory doubles) ──────────────────────────────────
class FakePool:
    """asyncpg pool double — captures the INSERT and returns a synthetic row."""

    def __init__(self, *, is_insert=True):
        self.executed: list = []
        self._is_insert = is_insert

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self_inner):
                return _Conn(pool)

            async def __aexit__(self_inner, *a):
                return False

        return _Ctx()


class _Conn:
    def __init__(self, pool):
        self._pool = pool

    async def fetchrow(self, sql, *args):
        self._pool.executed.append(("fetchrow", args))
        return {
            "vehicle_ulid": args[0], "thumb_url": None,
            "is_insert": self._pool._is_insert, "price_dropped": False,
            "prev_price_eur": args[22],
        }

    async def execute(self, sql, *args):
        self._pool.executed.append(("execute", args))


class FakeRedis:
    def __init__(self):
        self.streams: dict[str, list] = {}
        self.acked: list[str] = []

    async def xadd(self, stream, fields, maxlen=None, approximate=None):
        self.streams.setdefault(stream, []).append(fields)
        return "0-1"

    async def xack(self, stream, group, msg_id):
        self.acked.append(msg_id)

    def seed_pending(self, batch):
        self._pending = list(batch)

    async def xautoclaim(self, stream, group, consumer, min_idle_time, start_id, count):
        batch = getattr(self, "_pending", [])
        self._pending = []
        return ["0-0", batch, []]


@pytest.mark.unit
def test_reclaim_pending_reprocesses_stranded_entry():
    # A message A7 read but left un-ACKed (persist raised) must be reclaimed and
    # re-persisted — idempotent ON CONFLICT means re-processing never duplicates.
    pool, rdb, stats = FakePool(), FakeRedis(), RichStats()
    env = {"payload": json.dumps(_payload()), "source": "viabovag.nl", "channel": "SCRAPER"}
    rdb.seed_pending([("9-0", env)])
    n = _run(rc.reclaim_pending(pool, rdb, stats, consumer="c", idle_ms=60000, count=10,
                                rates={"EUR": Decimal(1)}))
    assert n == 1 and stats.persisted == 1
    assert rdb.acked == ["9-0"]
    assert rc.MEILI_SYNC_STREAM in rdb.streams


@pytest.mark.unit
def test_reclaim_tombstone_is_acked():
    pool, rdb, stats = FakePool(), FakeRedis(), RichStats()
    rdb.seed_pending([("10-0", {})])
    n = _run(rc.reclaim_pending(pool, rdb, stats, consumer="c", idle_ms=60000, count=10))
    assert n == 0 and rdb.acked == ["10-0"] and stats.persisted == 0


@pytest.mark.unit
def test_process_message_persists_and_emits_meili():
    pool, rdb, stats = FakePool(), FakeRedis(), RichStats()
    env = {"payload": json.dumps(_payload()), "source": "gaspedaal.nl", "channel": "SCRAPER"}

    _run(rc.process_message(pool, rdb, "1-0", env, stats, rates={"EUR": Decimal(1)}))

    assert stats.persisted == 1
    assert rdb.acked == ["1-0"]
    assert len(rdb.streams[rc.MEILI_SYNC_STREAM]) == 1
    assert len(rdb.streams[rc.PRICE_EVENTS_STREAM]) == 1  # EUR known → price event
    meili = json.loads(rdb.streams[rc.MEILI_SYNC_STREAM][0]["payload"])
    assert meili["make"] == "Audi" and meili["price_eur"] == 18500.0


@pytest.mark.unit
def test_process_message_rejects_invalid_and_acks():
    pool, rdb, stats = FakePool(), FakeRedis(), RichStats()
    env = {"payload": json.dumps(_payload(make="")), "source": "x", "channel": "SCRAPER"}

    _run(rc.process_message(pool, rdb, "2-0", env, stats, rates={"EUR": Decimal(1)}))

    assert stats.rejected == 1 and stats.persisted == 0
    assert rdb.acked == ["2-0"]                 # rejected garbage is still acked
    assert pool.executed == []                  # never hit the DB


@pytest.mark.unit
def test_process_message_writes_vin_history_on_insert():
    pool, rdb, stats = FakePool(is_insert=True), FakeRedis(), RichStats()
    env = {"payload": json.dumps(_payload(vin="WAUZZZ8E56A123456")),
           "source": "gaspedaal.nl", "channel": "SCRAPER"}

    _run(rc.process_message(pool, rdb, "3-0", env, stats, rates={"EUR": Decimal(1)}))

    # one fetchrow (vehicles) + LISTING + MILEAGE (mileage>0) executes
    kinds = [k for k, _ in pool.executed]
    assert kinds.count("fetchrow") == 1
    assert kinds.count("execute") == 2


@pytest.mark.unit
def test_process_message_bad_json_acks_and_rejects():
    pool, rdb, stats = FakePool(), FakeRedis(), RichStats()
    env = {"payload": "{not json", "source": "x", "channel": "SCRAPER"}

    _run(rc.process_message(pool, rdb, "4-0", env, stats))

    assert stats.rejected == 1
    assert rdb.acked == ["4-0"]
