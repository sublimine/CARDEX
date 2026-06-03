"""
Pipeline tests — parse, normalize, schema hashing, delta, quality gates, DLQ.

Every stage is exercised in isolation, no network or browser: parse takes HTML
strings, normalize takes raw dicts, delta takes plain maps, and the two DB-backed
writers (DLQ, indirectly quality's poison gate) run against the in-memory `conn`.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from scrapers.pipeline import delta, dlq, normalize, parse, quality
from scrapers.pipeline.schema import (
    VatMode,
    VehicleRecord,
    content_fingerprint,
    price_hash,
)

# ── parse ─────────────────────────────────────────────────────────────────────
_JSONLD_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Car","brand":{"name":"BMW"},
 "model":"320d","vehicleModelDate":"2019",
 "mileageFromOdometer":{"value":"85000"},"fuelType":"Diesel",
 "vehicleTransmission":"Automatic","color":"black",
 "vehicleIdentificationNumber":"WBA8E9G50GNT12345",
 "image":["https://cdn.portal.de/1.jpg","https://cdn.portal.de/2.jpg"],
 "offers":{"@type":"Offer","price":"24900","priceCurrency":"EUR"}}
</script></head><body>listing</body></html>
"""


@pytest.mark.unit
def test_parse_jsonld_extracts_core_fields():
    raw = parse.parse_jsonld(_JSONLD_HTML)
    assert raw["make"] == "BMW"
    assert raw["model"] == "320d"
    assert raw["year"] == "2019"
    assert raw["price"] == "24900"
    assert raw["currency"] == "EUR"
    assert raw["images"] == ["https://cdn.portal.de/1.jpg", "https://cdn.portal.de/2.jpg"]


@pytest.mark.unit
def test_parse_jsonld_returns_empty_without_vehicle_type():
    html = '<script type="application/ld+json">{"@type":"Article","headline":"x"}</script>'
    assert parse.parse_jsonld(html) == {}


@pytest.mark.unit
def test_jsonld_types_collects_all_types():
    html = (
        '<script type="application/ld+json">{"@type":"Article"}</script>'
        '<script type="application/ld+json">{"@type":["Car","Product"]}</script>'
    )
    assert parse.jsonld_types(html) == {"article", "car", "product"}


@pytest.mark.unit
def test_parse_og_meta_fallback():
    html = (
        '<meta property="og:title" content="Audi A4">'
        '<meta property="og:image" content="https://cdn.portal.de/a.jpg">'
        '<meta property="product:price:amount" content="18500">'
        '<meta property="product:price:currency" content="EUR">'
    )
    raw = parse.parse_og_meta(html)
    assert raw["title"] == "Audi A4"
    assert raw["price"] == "18500"
    assert raw["images"] == ["https://cdn.portal.de/a.jpg"]


@pytest.mark.unit
def test_parse_heuristics_year_mileage_price():
    html = "Bj. 2017, 120.000 km, nur 12.500 EUR"
    raw = parse.parse_heuristics(html)
    assert raw["year"] == "2017"
    # The mileage regex keeps trailing space; normalize.parse_int_loose strips it later.
    assert raw["mileage"].strip() == "120.000"
    assert "12.500" in raw["price"]


@pytest.mark.unit
def test_parse_listing_jsonld_wins_over_heuristics():
    # JSON-LD year 2019 must survive even though the body text mentions 2010.
    html = _JSONLD_HTML + "<p>vendido en 2010 con 999.999 km</p>"
    raw = parse.parse_listing(html)
    assert raw["year"] == "2019"


# ── normalize ─────────────────────────────────────────────────────────────────
@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Diesel", normalize.FuelType.DIESEL),
        ("Gasoil", normalize.FuelType.DIESEL),       # 'gas' would mis-match gasoline
        ("Plug-in Hybrid", normalize.FuelType.HYBRID),
        ("Elektro", normalize.FuelType.ELECTRIC),
        ("Essence", normalize.FuelType.GASOLINE),
    ],
)
def test_normalize_fuel(raw, expected):
    assert normalize.normalize_fuel(raw) is expected


@pytest.mark.unit
def test_normalize_transmission_semi_before_automatic():
    assert normalize.normalize_transmission("Semi-automatique") is normalize.Transmission.SEMI_AUTOMATIC
    assert normalize.normalize_transmission("Automatik") is normalize.Transmission.AUTOMATIC


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("24.900,50", Decimal("24900.50")),   # EU: dot thousands, comma decimal
        ("24,900.50", Decimal("24900.50")),   # US: comma thousands, dot decimal
        ("12.500", Decimal("12500")),         # single dot + 3 digits → thousands
        ("12,5", Decimal("12.5")),            # single comma + 2 digits → decimal
        ("18 500 €", Decimal("18500")),       # spaces + symbol
    ],
)
def test_parse_decimal_separator_disambiguation(raw, expected):
    assert normalize.parse_decimal(raw) == expected


@pytest.mark.unit
def test_parse_decimal_rejects_garbage_and_negative():
    assert normalize.parse_decimal("n/a") is None
    assert normalize.parse_decimal(-5) is None


@pytest.mark.unit
def test_normalize_vin_strict_17_alnum():
    assert normalize.normalize_vin("wba8e9g50gnt12345") == "WBA8E9G50GNT12345"
    assert normalize.normalize_vin("TOO-SHORT") is None


@pytest.mark.unit
def test_parse_year_window():
    assert normalize.parse_year("Erstzulassung 2015") == 2015
    assert normalize.parse_year(1975) is None


@pytest.mark.unit
def test_to_record_end_to_end_from_jsonld():
    raw = parse.parse_listing(_JSONLD_HTML)
    rec = normalize.to_record(
        raw, source_url="https://portal.de/auto/123", source_domain="portal.de", country="de"
    )
    assert rec.make == "BMW"
    assert rec.year == 2019
    assert rec.mileage_km == 85000
    assert rec.fuel_type is normalize.FuelType.DIESEL
    assert rec.price_gross == Decimal("24900")
    assert rec.currency == "EUR"
    assert rec.country == "DE"
    assert rec.has_critical_fields()


# ── schema hashing ────────────────────────────────────────────────────────────
def _rec(**kw) -> VehicleRecord:
    base = dict(
        source_url="https://portal.de/auto/1",
        source_domain="portal.de",
        country="DE",
        make="BMW",
        model="320d",
        year=2019,
        price_gross=Decimal("24900"),
        currency="EUR",
        images=("https://cdn.portal.de/1.jpg",),
    )
    base.update(kw)
    return VehicleRecord(**base)


@pytest.mark.unit
def test_price_hash_changes_with_price_only():
    a = _rec(price_gross=Decimal("24900"))
    b = _rec(price_gross=Decimal("23900"))
    assert price_hash(a) != price_hash(b)


@pytest.mark.unit
def test_content_fingerprint_ignores_pointer_url():
    a = _rec(source_url="https://portal.de/auto/1")
    b = _rec(source_url="https://portal.de/auto/RELISTED")
    assert content_fingerprint(a) == content_fingerprint(b)


@pytest.mark.unit
def test_price_property_prefers_gross():
    rec = _rec(price_net=Decimal("20000"), price_gross=Decimal("24000"))
    assert rec.price == Decimal("24000")


# ── delta ─────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_compute_delta_new_gone_unchanged():
    prev = {"a": delta.PRICE_UNKNOWN, "b": delta.PRICE_UNKNOWN}
    cur = {"b": delta.PRICE_UNKNOWN, "c": delta.PRICE_UNKNOWN}
    res = delta.compute_delta(prev, cur)
    assert res.new == ("c",)
    assert res.gone == ("a",)
    assert res.unchanged == 1


@pytest.mark.unit
def test_compute_delta_price_change_requires_both_known():
    prev = {"a": "hash1"}
    cur = {"a": "hash2"}
    assert delta.compute_delta(prev, cur).price_changed == ("a",)
    # An unknown price on either side never fires a spurious change.
    assert delta.compute_delta({"a": "hash1"}, {"a": delta.PRICE_UNKNOWN}).price_changed == ()


@pytest.mark.unit
def test_cycle_from_urls_drops_root_links():
    cycle = delta.cycle_from_urls(["https://x.com/", "https://x.com/auto/9"])
    assert len(cycle) == 1


@pytest.mark.unit
def test_is_deep_link():
    assert delta.is_deep_link("https://x.com/auto/9")
    assert not delta.is_deep_link("https://x.com/")
    assert not delta.is_deep_link("https://x.com")


# ── quality gates ─────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_quality_passes_clean_record():
    assert quality.evaluate(_rec(), current_year=2026).ok


@pytest.mark.unit
@pytest.mark.parametrize(
    "kw,failure",
    [
        (dict(price_gross=Decimal("600000")), quality.QualityFailure.PRICE_OUT_OF_RANGE),
        (dict(price_gross=Decimal("0")), quality.QualityFailure.PRICE_OUT_OF_RANGE),
        (dict(year=1970), quality.QualityFailure.YEAR_OUT_OF_RANGE),
        (dict(mileage_km=2_000_000), quality.QualityFailure.MILEAGE_OUT_OF_RANGE),
        (dict(source_url="https://x.com/"), quality.QualityFailure.URL_NOT_DEEP_LINK),
    ],
)
def test_quality_structural_failures(kw, failure):
    verdict = quality.evaluate(_rec(**kw), current_year=2026)
    assert not verdict.ok
    assert failure in verdict.failures


@pytest.mark.unit
def test_quality_allows_absent_fields():
    # None price/year/mileage are completeness concerns, not validity failures.
    rec = _rec(price_gross=None, price_net=None, year=None, mileage_km=None)
    assert quality.evaluate(rec, current_year=2026).ok


@pytest.mark.unit
def test_quality_next_model_year_allowed():
    assert quality.evaluate(_rec(year=2027), current_year=2026).ok


@pytest.mark.unit
def test_quality_gate2_poison_marks_not_ok():
    html = '<script type="application/ld+json">{"@type":"Article"}</script>' + "x" * 100
    verdict = quality.evaluate(_rec(), html=html, current_year=2026)
    assert verdict.poison is not None and verdict.poison.is_poison
    assert quality.QualityFailure.POISON_DETECTED in verdict.failures


@pytest.mark.unit
def test_coherence_discrepancies_flags_divergent_vin_price():
    vin = "WBA8E9G50GNT12345"
    recs = [
        _rec(vin=vin, price_gross=Decimal("24900")),
        _rec(vin=vin, price_gross=Decimal("22900")),
        _rec(vin="WDB1234567890ABCD", price_gross=Decimal("30000")),
    ]
    discrepancies = quality.coherence_discrepancies(recs)
    assert len(discrepancies) == 1
    assert discrepancies[0].vin == vin
    assert discrepancies[0].prices == (Decimal("22900"), Decimal("24900"))


@pytest.mark.unit
def test_is_stale():
    now = 1_000_000_000
    assert quality.is_stale(now - 31 * 86_400, now=now)
    assert not quality.is_stale(now - 29 * 86_400, now=now)


# ── DLQ ───────────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_dlq_recovery_routing():
    assert dlq.recovery_for(dlq.DlqReason.FETCH_ERROR).delay_s == 3_600
    assert dlq.recovery_for(dlq.DlqReason.SOFT_BLOCK).premium_required
    assert dlq.recovery_for(dlq.DlqReason.PARSE_ERROR).needs_human
    assert dlq.recovery_for(dlq.DlqReason.POISON_DETECTED).terminal
    assert not dlq.recovery_for(dlq.DlqReason.POISON_DETECTED).retryable


@pytest.mark.unit
def test_dlq_rate_limited_honors_header():
    assert dlq.recovery_for(dlq.DlqReason.RATE_LIMITED, retry_after_header="300").delay_s == 300
    # Unparseable header falls back to the default.
    assert dlq.recovery_for(dlq.DlqReason.RATE_LIMITED, retry_after_header="soon").delay_s == 60


@pytest.mark.unit
def test_dlq_record_failure_upserts(conn):
    now = 1_000_000_000
    dlq.record_failure(conn, url="https://x.com/a/1", portal="portal", reason=dlq.DlqReason.FETCH_ERROR, now=now)
    dlq.record_failure(conn, url="https://x.com/a/1", portal="portal", reason=dlq.DlqReason.FETCH_ERROR, now=now + 10)
    row = conn.execute("SELECT fail_count, retry_after FROM dlq").fetchone()
    assert row["fail_count"] == 2
    assert row["retry_after"] == now + 10 + 3_600
    assert dlq.size(conn) == 1


@pytest.mark.unit
def test_dlq_terminal_reason_has_no_retry(conn):
    now = 1_000_000_000
    dlq.record_failure(conn, url="https://x.com/p/1", portal="portal", reason=dlq.DlqReason.POISON_DETECTED, now=now)
    assert dlq.due_items(conn, now=now + 10**9) == []  # never becomes due


@pytest.mark.unit
def test_dlq_due_items_and_resolve(conn):
    now = 1_000_000_000
    dlq.record_failure(conn, url="https://x.com/r/1", portal="portal", reason=dlq.DlqReason.RATE_LIMITED,
                       retry_after_header="60", now=now)
    assert dlq.due_items(conn, now=now) == []          # not yet due
    due = dlq.due_items(conn, now=now + 61)
    assert len(due) == 1
    dlq.resolve(conn, due[0]["url_hash"])
    assert dlq.size(conn) == 0
