"""as24_dealers discovery source — pure transform + adapter tests (no network)."""
from __future__ import annotations

import asyncio

import pytest

from scrapers.discovery.sources.as24_dealers import (
    AS24DealerSource,
    parse_address,
    parse_dealer,
)


@pytest.mark.unit
def test_parse_address_strict_format():
    street, postcode, city = parse_address("Am Baumgarten  3+7, 91463 Dietersheim, DE")
    assert street == "Am Baumgarten  3+7"
    assert postcode == "91463"
    assert city == "Dietersheim"


@pytest.mark.unit
def test_parse_address_nl_postcode_keeps_letter_suffix():
    # NL "NNNN LL" postcode -> the 2-letter suffix belongs to the postcode, not the city.
    street, postcode, city = parse_address("Dorpsstraat 1, 8446 DB HEERENVEEN, NL", "NL")
    assert postcode == "8446 DB" and city == "HEERENVEEN"


@pytest.mark.unit
def test_parse_address_es_city_with_leading_two_letter_word_not_eaten():
    # The NL rule must NOT apply to ES: "LA MORERA" stays the city, postcode stays digits.
    street, postcode, city = parse_address("Calle Sevilla 3, 41710 LA MORERA, ES", "ES")
    assert postcode == "41710" and city == "LA MORERA"


@pytest.mark.unit
def test_parse_address_falls_back_to_raw_on_miss():
    # No "<postcode> <city>, <CC>" tail -> keep the raw string as street, no postcode/city.
    street, postcode, city = parse_address("Postfach 12, irgendwo")
    assert street == "Postfach 12, irgendwo"
    assert postcode is None and city is None
    assert parse_address("") == (None, None, None)
    assert parse_address(None) == (None, None, None)


@pytest.mark.unit
def test_parse_dealer_maps_identity_row():
    rec = {
        "customerId": 5742, "companyName": "Auto Zeilinger GmbH", "slug": "auto-zeilinger-gmbh",
        "address": "Am Baumgarten  3+7, 91463 Dietersheim, DE", "rating": 4.81, "ratingCount": 3138,
    }
    c = parse_dealer(rec, "DE")
    assert c["domain"] is None                       # identity row (resolved downstream)
    assert c["country"] == "DE" and c["source"] == "portal:autoscout24"
    assert c["source_layer"] == 2
    assert c["registry_id"] == "5742"                # AS24 customerId, dedup key
    assert c["name"] == "Auto Zeilinger GmbH"
    assert c["address"] == "Am Baumgarten  3+7"
    assert c["postcode"] == "91463" and c["city"] == "Dietersheim"
    assert c["external_refs"]["as24_customer_id"] == 5742
    assert c["external_refs"]["slug"] == "auto-zeilinger-gmbh"
    assert c["external_refs"]["rating"] == 4.81


@pytest.mark.unit
def test_parse_dealer_rejects_incomplete_rows():
    assert parse_dealer({"customerId": 1}, "DE") is None              # no name
    assert parse_dealer({"companyName": "X"}, "DE") is None           # no customerId
    assert parse_dealer({"customerId": 0, "companyName": "Zero Co"}, "DE")["registry_id"] == "0"


# ── AS24DealerSource (orchestrator adapter): paginates, yields, honours limit/gate ──
class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeClient:
    """httpx-shaped double: returns ``total`` once and paginates by pageIndex."""

    def __init__(self, pages: dict[int, list[dict]], total: int):
        self._pages, self._total = pages, total

    async def get(self, url, params=None, headers=None):
        pi = (params or {}).get("pageIndex", 1)
        return _FakeResp({"results": self._pages.get(pi, []), "totalDealers": self._total})


async def _collect(agen):
    return [x async for x in agen]


def _dealer(cid: str, name: str) -> dict:
    return {"customerId": cid, "companyName": name,
            "address": f"Street {cid}, 10000 City{cid}, DE", "slug": f"s{cid}"}


@pytest.mark.unit
def test_source_paginates_until_short_page():
    # size=2: pages 1 and 2 are full (last-page signal is "len < size"), page 3 is the short tail.
    pages = {1: [_dealer("1", "A"), _dealer("2", "B")],
             2: [_dealer("3", "C"), _dealer("4", "D")],
             3: [_dealer("5", "E")]}
    src = AS24DealerSource(_FakeClient(pages, total=5), size=2)
    cands = asyncio.run(_collect(src.discover("DE")))
    assert [c["registry_id"] for c in cands] == ["1", "2", "3", "4", "5"]
    assert all(c["source"] == "portal:autoscout24" and c["domain"] is None for c in cands)


@pytest.mark.unit
def test_source_stops_on_empty_page_independent_of_total():
    # totalDealers lies (says 999) but the data dries up — we trust the data, not the count.
    pages = {1: [_dealer("1", "A"), _dealer("2", "B")], 2: []}
    src = AS24DealerSource(_FakeClient(pages, total=999), size=2)
    cands = asyncio.run(_collect(src.discover("DE")))
    assert [c["registry_id"] for c in cands] == ["1", "2"]


@pytest.mark.unit
def test_source_honours_limit():
    pages = {1: [_dealer(str(i), f"D{i}") for i in range(10)],
             2: [_dealer(str(i), f"D{i}") for i in range(10, 20)]}
    src = AS24DealerSource(_FakeClient(pages, total=20), limit=5, size=10)
    cands = asyncio.run(_collect(src.discover("DE")))
    assert len(cands) == 5


@pytest.mark.unit
def test_source_skips_uncovered_country():
    # CH is not served by the dealer-search dataset -> yield nothing, no fetch contract assumed.
    src = AS24DealerSource(_FakeClient({1: [_dealer("1", "A")]}, total=1))
    assert asyncio.run(_collect(src.discover("CH"))) == []
