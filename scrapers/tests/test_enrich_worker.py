"""
A6 enrich_worker tests — the L1→L2 seam, no network or live Redis.

Coverage:
  * record_to_payload   C6→C7 field mapping, enum→str, price→float,
                        and the H1 source_id guarantee (listing_id ← url_hash)
  * enrich_one          ok path (MapFetcher → payload), reject reasons
  * process_message     at-least-once routing — emit+ack, permanent→DLQ+ack,
                        transient→no ack — against an in-memory Redis double
  * _is_permanent       transient vs permanent classification

Mirrors test_generic_extractor's MapFetcher convention: every async path runs
synchronously via asyncio.run, all fixtures in-memory.
"""
from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import pytest

from scrapers import enrich_worker as ew
from scrapers.enrich_worker import (
    DEFAULT_CHANNEL,
    INGESTION_STREAM,
    EnrichStats,
    enrich_one,
    process_message,
    record_to_payload,
)
from scrapers.pipeline.generic_extractor import FetchResult
from scrapers.pipeline.schema import FuelType, Transmission, VehicleRecord


# ── in-memory transport (same shape as test_generic_extractor) ─────────────────
class MapFetcher:
    def __init__(self, pages: dict[str, tuple[int, bytes]], *, fail_urls=()):
        self._pages = pages
        self._fail = set(fail_urls)

    async def __call__(self, url: str) -> FetchResult:
        if url in self._fail:
            raise ConnectionError("simulated transport fault")
        if url in self._pages:
            status, body = self._pages[url]
            return FetchResult(url=url, status_code=status, body=body)
        return FetchResult(url=url, status_code=404, body=b"")


# ── in-memory Redis double — only the methods the worker calls ─────────────────
class FakeRedis:
    def __init__(self):
        self.ingestion: list[dict] = []
        self.dlq: list[dict] = []
        self.acked: list[str] = []

    async def xadd(self, stream, fields, maxlen=None, approximate=None):
        if stream == INGESTION_STREAM:
            self.ingestion.append(fields)
        elif stream == ew.DLQ_STREAM:
            self.dlq.append(fields)
        return "0-1"

    async def xack(self, stream, group, msg_id):
        self.acked.append(msg_id)

    # XAUTOCLAIM double: returns the seeded stranded batch once, then drains.
    def seed_pending(self, batch):
        self._pending = list(batch)

    async def xautoclaim(self, stream, group, consumer, min_idle_time, start_id, count):
        batch = getattr(self, "_pending", [])
        self._pending = []
        return ["0-0", batch, []]


_PAD = "<div class='spec'><span></span></div>" * 600


def _detail_html(*, make="BMW", model="320d", year="2019", price="24900",
                 vin="WBA8E9G50GNT12345",
                 images=("https://cdn.x.de/1.jpg", "https://cdn.x.de/2.jpg")) -> bytes:
    img_json = ",".join(f'"{u}"' for u in images)
    return (
        "<html><head>"
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Car",'
        f'"brand":{{"name":"{make}"}},"model":"{model}",'
        f'"vehicleModelDate":"{year}",'
        '"mileageFromOdometer":{"value":"85000"},"fuelType":"Diesel",'
        '"vehicleTransmission":"Automatic","color":"black",'
        f'"vehicleIdentificationNumber":"{vin}",'
        f'"image":[{img_json}],'
        f'"offers":{{"@type":"Offer","price":"{price}","priceCurrency":"EUR"}}}}'
        "</script></head><body>" + _PAD + "</body></html>"
    ).encode("utf-8")


_EMPTY_HTML = b"<html><body>Welcome to our dealership.</body></html>"


def _run(coro):
    return asyncio.run(coro)


# ── record_to_payload (pure C6→C7) ─────────────────────────────────────────────
@pytest.mark.unit
def test_record_to_payload_maps_core_fields():
    rec = VehicleRecord(
        source_url="https://gaspedaal.nl/audi/a4/123",
        source_domain="gaspedaal.nl",
        country="NL",
        source_listing_id="LST-9",
        vin="WAUZZZ8E56A123456",
        make="Audi", model="A4", year=2018, mileage_km=90000,
        fuel_type=FuelType.DIESEL, transmission=Transmission.AUTOMATIC,
        power_kw=110, color="grey",
        price_gross=Decimal("18500"), currency="EUR",
        images=("https://cdn/1.jpg", "https://cdn/2.jpg"),
    )
    p = record_to_payload(rec, source_key="gaspedaal.nl", url_hash="abc123")

    assert p["source_url"] == "https://gaspedaal.nl/audi/a4/123"
    assert p["make"] == "Audi" and p["model"] == "A4" and p["year"] == 2018
    assert p["mileage_km"] == 90000 and p["power_kw"] == 110
    assert p["fuel_type"] == "diesel" and p["transmission"] == "automatic"
    assert p["price_raw"] == 18500.0 and isinstance(p["price_raw"], float)
    assert p["currency_raw"] == "EUR"
    assert p["source_country"] == "NL"
    assert p["photo_urls"] == ["https://cdn/1.jpg", "https://cdn/2.jpg"]
    assert p["thumbnail_url"] == "https://cdn/1.jpg"
    assert p["source_platform"] == "gaspedaal.nl"
    # the whole payload must be JSON-serializable (it crosses Redis as a string)
    json.dumps(p)


@pytest.mark.unit
def test_record_to_payload_h1_uses_real_listing_id_when_present():
    rec = VehicleRecord(
        source_url="https://x.nl/a/1", source_domain="x.nl", country="NL",
        source_listing_id="REAL-42", make="VW", model="Golf", year=2020,
        price_gross=Decimal("15000"), currency="EUR", images=("https://c/1.jpg",),
    )
    p = record_to_payload(rec, source_key="x.nl", url_hash="HASHVAL")
    assert p["source_listing_id"] == "REAL-42"


@pytest.mark.unit
def test_record_to_payload_h1_falls_back_to_url_hash():
    # H1: no platform listing id → derive source_listing_id from url_hash so the
    # downstream coalesce(source_id, source_listing_id) can never yield NULL.
    rec = VehicleRecord(
        source_url="https://x.nl/a/1", source_domain="x.nl", country="NL",
        source_listing_id=None, make="VW", model="Golf", year=2020,
        price_gross=Decimal("15000"), currency="EUR", images=("https://c/1.jpg",),
    )
    p = record_to_payload(rec, source_key="x.nl", url_hash="DERIVED_HASH")
    assert p["source_listing_id"] == "DERIVED_HASH"
    assert p["source_listing_id"]  # never empty


@pytest.mark.unit
def test_record_to_payload_price_net_when_no_gross():
    rec = VehicleRecord(
        source_url="https://x.nl/a/1", source_domain="x.nl", country="NL",
        make="VW", model="Golf", year=2020,
        price_net=Decimal("12000"), currency="EUR", images=("https://c/1.jpg",),
    )
    p = record_to_payload(rec, source_key="x.nl", url_hash="h")
    assert p["price_raw"] == 12000.0


# ── enrich_one ─────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_enrich_one_ok_produces_payload():
    url = "https://dealer.de/vehicles/bmw-320d-1"
    fetcher = MapFetcher({url: (200, _detail_html())})
    fields = {"h": "URLHASH1", "u": url, "s": "dealer.de", "c": "DE"}
    payload, reason = _run(enrich_one(fields, fetcher))
    assert reason == "ok"
    assert payload["make"] == "BMW" and payload["model"] == "320d"
    assert payload["year"] == 2019
    assert payload["price_raw"] == 24900.0
    assert payload["currency_raw"] == "EUR"
    assert payload["source_country"] == "DE"
    # fixture carries a VIN but no sku/@id → listing_id derived from url_hash (H1)
    assert payload["source_listing_id"] == "URLHASH1"
    assert payload["vin"] == "WBA8E9G50GNT12345"


@pytest.mark.unit
def test_enrich_one_malformed_pointer():
    payload, reason = _run(enrich_one({"h": "", "u": ""}, MapFetcher({})))
    assert payload is None
    assert reason == "rejected:malformed_pointer"


@pytest.mark.unit
def test_enrich_one_fetch_error_is_transient():
    url = "https://dealer.de/vehicles/x-1"
    fetcher = MapFetcher({}, fail_urls={url})
    fields = {"h": "h", "u": url, "s": "dealer.de", "c": "DE"}
    payload, reason = _run(enrich_one(fields, fetcher))
    assert payload is None
    assert reason == "fetch_error"
    assert not ew._is_permanent(reason)


@pytest.mark.unit
def test_enrich_one_no_fields_is_permanent():
    url = "https://dealer.de/vehicles/blank-1"
    fetcher = MapFetcher({url: (200, _EMPTY_HTML)})
    fields = {"h": "h", "u": url, "s": "dealer.de", "c": "DE"}
    payload, reason = _run(enrich_one(fields, fetcher))
    assert payload is None
    assert reason == "no_fields"
    assert ew._is_permanent(reason)


# ── process_message routing (at-least-once) ────────────────────────────────────
@pytest.mark.unit
def test_process_message_emits_and_acks_on_success():
    url = "https://dealer.de/vehicles/bmw-320d-1"
    fetcher = MapFetcher({url: (200, _detail_html())})
    rdb, stats = FakeRedis(), EnrichStats()
    fields = {"h": "URLHASH1", "u": url, "s": "dealer.de", "c": "DE"}

    _run(process_message(rdb, fetcher, "5-0", fields, stats))

    assert stats.emitted == 1 and stats.dlq == 0 and stats.transient == 0
    assert rdb.acked == ["5-0"]
    assert len(rdb.ingestion) == 1
    env = rdb.ingestion[0]
    assert env["source"] == "dealer.de" and env["channel"] == DEFAULT_CHANNEL
    payload = json.loads(env["payload"])
    assert payload["make"] == "BMW" and payload["source_listing_id"] == "URLHASH1"


@pytest.mark.unit
def test_process_message_permanent_failure_goes_to_dlq_and_acks():
    url = "https://dealer.de/vehicles/blank-1"
    fetcher = MapFetcher({url: (200, _EMPTY_HTML)})
    rdb, stats = FakeRedis(), EnrichStats()
    fields = {"h": "h", "u": url, "s": "dealer.de", "c": "DE"}

    _run(process_message(rdb, fetcher, "6-0", fields, stats))

    assert stats.dlq == 1 and stats.emitted == 0
    assert rdb.acked == ["6-0"]            # permanent → acked (not retried)
    assert len(rdb.ingestion) == 0
    assert rdb.dlq[0]["reason"] == "no_fields"


@pytest.mark.unit
def test_process_message_transient_failure_is_not_acked():
    url = "https://dealer.de/vehicles/x-1"
    fetcher = MapFetcher({}, fail_urls={url})
    rdb, stats = FakeRedis(), EnrichStats()
    fields = {"h": "h", "u": url, "s": "dealer.de", "c": "DE"}

    _run(process_message(rdb, fetcher, "7-0", fields, stats))

    assert stats.transient == 1
    assert rdb.acked == []                 # transient → NOT acked → reclaim retries
    assert len(rdb.ingestion) == 0 and len(rdb.dlq) == 0


@pytest.mark.unit
def test_process_message_decodes_byte_fields():
    # producer (indexer.py) writes with decode_responses=False → bytes fields
    url = "https://dealer.de/vehicles/bmw-320d-1"
    fetcher = MapFetcher({url: (200, _detail_html())})
    rdb, stats = FakeRedis(), EnrichStats()
    fields = {b"h": b"URLHASH1", b"u": url.encode(), b"s": b"dealer.de", b"c": b"DE"}

    _run(process_message(rdb, fetcher, "8-0", fields, stats))

    assert stats.emitted == 1
    payload = json.loads(rdb.ingestion[0]["payload"])
    assert payload["make"] == "BMW"


# ── reclaim (XAUTOCLAIM) — H1 durability ───────────────────────────────────────
@pytest.mark.unit
def test_reclaim_pending_reprocesses_stranded_entry():
    # A message a prior consumer read but never ACKed (transient fault) must be
    # reclaimed from the PEL and re-enriched — not lost.
    url = "https://dealer.de/vehicles/audi-a4-99"
    fetcher = MapFetcher({url: (200, _detail_html(make="Audi", model="A4"))})
    rdb, stats = FakeRedis(), EnrichStats()
    rdb.seed_pending([("7-0", {"h": "STRAND1", "u": url, "s": "dealer.de", "c": "DE"})])

    n = _run(ew.reclaim_pending(rdb, fetcher, stats, consumer="c", idle_ms=60000, count=10))

    assert n == 1 and stats.emitted == 1
    assert len(rdb.ingestion) == 1 and rdb.acked == ["7-0"]


@pytest.mark.unit
def test_reclaim_tombstone_is_acked_not_processed():
    # An entry deleted from the stream after being read comes back with empty
    # fields → ACK to clear it from the PEL, never reprocess.
    rdb, stats = FakeRedis(), EnrichStats()
    rdb.seed_pending([("8-0", {})])
    n = _run(ew.reclaim_pending(rdb, MapFetcher({}), stats, consumer="c", idle_ms=60000, count=10))
    assert n == 0 and rdb.acked == ["8-0"] and stats.emitted == 0
