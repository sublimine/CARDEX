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
import hashlib
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

    def __init__(self, *, is_insert=True, price_changed=False, price_dropped=False, prev_price_eur=None):
        self.executed: list = []
        self._is_insert = is_insert
        self._price_changed = price_changed
        self._price_dropped = price_dropped
        self._prev_price_eur = prev_price_eur

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
            "is_insert": self._pool._is_insert,
            "price_dropped": self._pool._price_dropped,
            "price_changed": self._pool._price_changed,
            "prev_price_eur": (
                self._pool._prev_price_eur if self._pool._prev_price_eur is not None else args[22]
            ),
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
def test_price_change_emits_event_any_direction():
    # An UPDATE (not insert) whose price changed → PRICE_CHANGE + MILEAGE = 2 executes.
    # (Regression guard for the always-false price_dropped bug: the event must fire.)
    pool = FakePool(is_insert=False, price_changed=True, prev_price_eur=Decimal(18000))
    rdb, stats = FakeRedis(), RichStats()
    env = {"payload": json.dumps(_payload(vin="WAUZZZ8E56A123456", price_raw=18500.0)),  # rise
           "source": "gaspedaal.nl", "channel": "SCRAPER"}
    _run(rc.process_message(pool, rdb, "5-0", env, stats, rates={"EUR": Decimal(1)}))
    kinds = [k for k, _ in pool.executed]
    assert kinds.count("fetchrow") == 1
    assert kinds.count("execute") == 2     # PRICE_CHANGE + MILEAGE (no LISTING: it is an update)


@pytest.mark.unit
def test_no_price_change_suppresses_event():
    # An UPDATE with no price change → only MILEAGE = 1 execute (no PRICE_CHANGE).
    pool = FakePool(is_insert=False, price_changed=False, prev_price_eur=Decimal(18500))
    rdb, stats = FakeRedis(), RichStats()
    env = {"payload": json.dumps(_payload(vin="WAUZZZ8E56A123456", price_raw=18500.0)),
           "source": "gaspedaal.nl", "channel": "SCRAPER"}
    _run(rc.process_message(pool, rdb, "6-0", env, stats, rates={"EUR": Decimal(1)}))
    kinds = [k for k, _ in pool.executed]
    assert kinds.count("execute") == 1     # MILEAGE only


@pytest.mark.unit
def test_process_message_bad_json_acks_and_rejects():
    pool, rdb, stats = FakePool(), FakeRedis(), RichStats()
    env = {"payload": "{not json", "source": "x", "channel": "SCRAPER"}

    _run(rc.process_message(pool, rdb, "4-0", env, stats))

    assert stats.rejected == 1
    assert rdb.acked == ["4-0"]


# ── entity linking (dealer cage → source_entities + vehicles.entity_ulid) ────────
def _se_ulid(key: str) -> str:
    return "se_" + hashlib.md5(key.encode()).hexdigest()


class EntityFakePool:
    """asyncpg pool double that also answers ``fetchval`` — exercises entity linking.

    ``schema``            → the to_regclass('source_entities') probe result.
    ``entity_row_exists`` → whether the post-upsert SELECT resolves a ulid (False
                            simulates the country-scope guard silently rejecting).
    """

    def __init__(self, *, schema: bool = True, entity_row_exists: bool = True):
        self.executed: list = []        # ("fetchrow"|"execute", sql, args)
        self.entity_upserts: list = []  # args of every source_entities INSERT
        self._schema = schema
        self._entity_row_exists = entity_row_exists

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self_inner):
                return _EntityConn(pool)

            async def __aexit__(self_inner, *a):
                return False

        return _Ctx()


class _EntityConn:
    def __init__(self, pool):
        self._pool = pool

    async def fetchval(self, sql, *args):
        if "to_regclass" in sql:
            return "source_entities" if self._pool._schema else None
        # SELECT entity_ulid FROM source_entities WHERE source_key = $1
        return _se_ulid(args[0]) if self._pool._entity_row_exists else None

    async def fetchrow(self, sql, *args):
        self._pool.executed.append(("fetchrow", sql, args))
        return {
            "vehicle_ulid": args[0], "thumb_url": None, "is_insert": True,
            "price_dropped": False, "price_changed": False, "prev_price_eur": None,
        }

    async def execute(self, sql, *args):
        if "source_entities" in sql:
            self._pool.entity_upserts.append(args)
        self._pool.executed.append(("execute", sql, args))


@pytest.fixture
def _fresh_entity_caches(monkeypatch):
    """Isolate the process-local entity caches per test."""
    monkeypatch.setattr(rc, "_entity_schema", None)
    monkeypatch.setattr(rc, "_entity_cache", {})


@pytest.mark.unit
def test_entity_sql_derivation_and_portal_sql_untouched():
    # Derived variant carries the link; the portal statement has ZERO entity surface.
    assert "$31" in rc._INSERT_VEHICLE_ENTITY_SQL
    assert "COALESCE(vehicles.entity_ulid, EXCLUDED.entity_ulid)" in rc._INSERT_VEHICLE_ENTITY_SQL
    assert "entity_ulid" not in rc._INSERT_VEHICLE_SQL


@pytest.mark.unit
def test_persist_one_dealer_registers_entity_and_links(_fresh_entity_caches):
    pool = EntityFakePool()
    result, reason = _run(rc.persist_one(
        pool, _payload(), source="pouwtest.nl", channel="SCRAPER",
        rates={"EUR": Decimal(1)}, entity_kind="dealer",
    ))
    assert reason == "ok" and result is not None
    # (a) the dealer entity was upserted (kind='dealer', country from the payload)
    assert pool.entity_upserts == [("pouwtest.nl", "dealer", "NL")]
    # (b) the vehicles INSERT used the entity variant with $31 = 'se_'||md5(source)
    kind, sql, args = pool.executed[-1]
    assert kind == "fetchrow" and sql is rc._INSERT_VEHICLE_ENTITY_SQL
    assert len(args) == 31 and args[30] == _se_ulid("pouwtest.nl")


@pytest.mark.unit
def test_persist_one_default_keeps_portal_contract(_fresh_entity_caches):
    # No entity_kind (every existing portal/script caller) → byte-identical behavior.
    pool = EntityFakePool()
    result, reason = _run(rc.persist_one(
        pool, _payload(), source="gaspedaal.nl", channel="SCRAPER", rates={"EUR": Decimal(1)},
    ))
    assert reason == "ok" and result is not None
    assert pool.entity_upserts == []
    kind, sql, args = pool.executed[-1]
    assert sql is rc._INSERT_VEHICLE_SQL and len(args) == 30


@pytest.mark.unit
def test_persist_one_dealer_unlinked_when_scope_guard_rejects(_fresh_entity_caches):
    # Trigger silently skipped the entity row → fall back to the unlinked INSERT (FK-safe).
    pool = EntityFakePool(entity_row_exists=False)
    result, reason = _run(rc.persist_one(
        pool, _payload(source_country="IT"), source="fuoriscope.it", channel="SCRAPER",
        rates={"EUR": Decimal(1)}, entity_kind="dealer",
    ))
    assert reason == "ok" and result is not None
    assert len(pool.entity_upserts) == 1          # upsert attempted (idempotent no-op)
    kind, sql, args = pool.executed[-1]
    assert sql is rc._INSERT_VEHICLE_SQL and len(args) == 30


@pytest.mark.unit
def test_persist_one_dealer_degrades_without_entity_schema(_fresh_entity_caches):
    # Pre-migration envs: source_entities absent → no upsert, legacy SQL.
    pool = EntityFakePool(schema=False)
    result, reason = _run(rc.persist_one(
        pool, _payload(), source="dealer.nl", channel="SCRAPER",
        rates={"EUR": Decimal(1)}, entity_kind="dealer",
    ))
    assert reason == "ok" and result is not None
    assert pool.entity_upserts == []
    kind, sql, args = pool.executed[-1]
    assert sql is rc._INSERT_VEHICLE_SQL and len(args) == 30


@pytest.mark.unit
def test_entity_upserted_once_per_source_per_process(_fresh_entity_caches):
    # Steady state: the process cache keeps it at ONE upsert per source_key (MVCC-light).
    pool = EntityFakePool()
    for i in (1, 2, 3):
        _run(rc.persist_one(
            pool, _payload(source_url=f"https://dealer.nl/car/{i}"),
            source="dealer.nl", channel="SCRAPER",
            rates={"EUR": Decimal(1)}, entity_kind="dealer",
        ))
    assert len(pool.entity_upserts) == 1
    assert all(a[30] == _se_ulid("dealer.nl") for k, s, a in pool.executed if k == "fetchrow")


@pytest.mark.unit
def test_unknown_source_never_registers_an_entity(_fresh_entity_caches):
    pool = EntityFakePool()
    result, reason = _run(rc.persist_one(
        pool, _payload(), source="UNKNOWN", channel="SCRAPER",
        rates={"EUR": Decimal(1)}, entity_kind="dealer",
    ))
    assert reason == "ok" and result is not None
    assert pool.entity_upserts == []
    kind, sql, args = pool.executed[-1]
    assert sql is rc._INSERT_VEHICLE_SQL and len(args) == 30


@pytest.mark.unit
def test_run_rejects_invalid_entity_kind():
    with pytest.raises(ValueError):
        _run(rc.run(entity_kind="bogus"))   # fails fast, before any PG/Redis connect
