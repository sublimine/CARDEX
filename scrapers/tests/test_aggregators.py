"""
Unit tests for the aggregator connectors (auto-api.com, carapis.com).

Transport is injected: a `FakeApi` serves queued in-memory responses and records
every `ApiRequest`, so the tests assert both behaviour (key-gating, pagination,
error mapping) and the exact request shape (URL, params, auth header) without any
network. Coroutines are driven synchronously via `asyncio.run` — the convention
used across this suite.
"""
from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import pytest

from scrapers.aggregators import auto_api, carapis
from scrapers.aggregators.transport import (
    AggregatorAuthError,
    AggregatorError,
    AggregatorPull,
    ApiRequest,
    ApiResponse,
    AggregatorRateLimited,
    MissingApiKeyError,
    clean_params,
    host_of,
)
from scrapers.pipeline.schema import FuelType, Transmission, VehicleRecord

pytestmark = pytest.mark.unit


# ── test transport ────────────────────────────────────────────────────────────
class FakeApi:
    """Injected fetcher: serves queued responses in order, records every request.

    Each queued entry is either a ready `ApiResponse` or a callable
    `(ApiRequest) -> ApiResponse` for per-request shaping. `boom=True` makes the
    fetcher raise — used to prove a connector never touched the network.
    """

    def __init__(self, responses=None, *, boom: bool = False) -> None:
        self._responses = list(responses or [])
        self.requests: list[ApiRequest] = []
        self._boom = boom

    async def __call__(self, request: ApiRequest) -> ApiResponse:
        self.requests.append(request)
        if self._boom:
            raise AssertionError("network must not be touched")
        item = self._responses.pop(0)
        return item(request) if callable(item) else item


def _resp(payload, *, status: int = 200, headers=None) -> ApiResponse:
    body = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload).encode()
    return ApiResponse(status_code=status, body=bytes(body), headers=headers or {})


def _run(coro):
    return asyncio.run(coro)


# ── fixtures: verified per-listing shapes ──────────────────────────────────────
def _auto_api_offer(*, inner_id="A1", mark="BMW", model="320d", year=2020, km=45000,
                    price=28900, url="https://www.autoscout24.de/angebote/A1",
                    images=("https://img/1.jpg",), engine="Diesel",
                    transmission="Automatic", body="Sedan", color="black"):
    """One auto-api `OfferData` (types.go field names: mark, km_age, …)."""
    return {
        "inner_id": inner_id,
        "url": url,
        "mark": mark,
        "model": model,
        "generation": "G20",
        "year": year,
        "km_age": km,
        "price": price,
        "engine_type": engine,
        "transmission_type": transmission,
        "body_type": body,
        "color": color,
        "displacement": 1995,
        "address": "München",
        "seller_type": "dealer",
        "is_dealer": True,
        "images": list(images),
    }


def _auto_api_envelope(offers, *, page=1, next_page=0, limit=50):
    return {
        "result": [{"id": i, "inner_id": o["inner_id"], "change_type": "added",
                    "created_at": "2026-06-03", "data": o} for i, o in enumerate(offers)],
        "meta": {"page": page, "next_page": next_page, "limit": limit},
    }


def _carapis_listing(*, lid=1, make="Renault", model="Clio", year=2019, mileage=60000,
                     price=12990, currency="EUR", url="https://www.lacentrale.fr/auto-1",
                     photos=("https://img/c1.jpg",), fuel="Gasoline", transmission="Manual"):
    """One carapis v2 listing (carapis.com/api/intro field names)."""
    return {
        "id": lid, "source": "lacentrale", "make": make, "model": model, "year": year,
        "mileage": mileage, "price": price, "currency": currency, "location": "Paris",
        "fuel_type": fuel, "transmission": transmission, "photos": list(photos),
        "dealer": "Garage X", "url": url,
    }


def _carapis_envelope(listings, *, count=None, page=1, limit=100):
    return {
        "count": len(listings) if count is None else count,
        "page": page, "limit": limit, "results": list(listings),
    }


# ── shared helpers ──────────────────────────────────────────────────────────
def test_host_of_strips_www_and_lowercases():
    assert host_of("https://WWW.Mobile.De/auto/123") == "mobile.de"
    assert host_of("https://lacentrale.fr/x") == "lacentrale.fr"
    assert host_of("") == ""
    assert host_of("not a url") == ""


def test_clean_params_drops_omitempty():
    out = clean_params({"a": "x", "b": "", "c": None, "d": 0, "e": 7, "f": "0"})
    assert out == {"a": "x", "e": "7", "f": "0"}


def test_aggregator_pull_success_rate():
    pull = AggregatorPull("x", "s", "DE", pages_fetched=1, seen=4,
                          records=(object(), object()), skipped=(("a", "r"),))
    assert pull.extracted == 2
    assert pull.success_rate == 0.5
    empty = AggregatorPull("x", "s", "DE", 0, 0, (), ())
    assert empty.success_rate == 0.0


# ── auto-api: key gating ──────────────────────────────────────────────────────
def test_auto_api_missing_key_raises_before_network():
    fake = FakeApi(boom=True)
    for key in ("", "   ", None):
        with pytest.raises(MissingApiKeyError) as exc:
            _run(auto_api.fetch_offers("autoscout24", fake, api_key=key, country="de"))
        assert "[NEEDS-KEY]" in str(exc.value)
    assert fake.requests == []  # never touched the network


# ── auto-api: mapping ──────────────────────────────────────────────────────────
def test_auto_api_maps_offerdata_to_record():
    fake = FakeApi([_resp(_auto_api_envelope([_auto_api_offer()]))])
    pull = _run(auto_api.fetch_offers("autoscout24", fake, api_key="k", country="de"))

    assert pull.extracted == 1 and pull.seen == 1 and pull.pages_fetched == 1
    rec: VehicleRecord = pull.records[0]
    assert rec.make == "BMW"  # mapped from `mark`
    assert rec.model == "320d"
    assert rec.year == 2020
    assert rec.mileage_km == 45000  # mapped from `km_age`
    assert rec.fuel_type is FuelType.DIESEL  # engine_type → fuel
    assert rec.transmission is Transmission.AUTOMATIC
    assert rec.price == Decimal("28900")
    assert rec.images == ("https://img/1.jpg",)
    assert rec.source_url == "https://www.autoscout24.de/angebote/A1"
    assert rec.source_domain == "autoscout24.de"  # derived from url host
    assert rec.country == "DE"
    assert rec.source_listing_id == "A1"
    assert rec.additional["seller_type"] == "dealer"
    assert rec.additional["generation"] == "G20"


def test_auto_api_request_shape_and_filters():
    fake = FakeApi([_resp(_auto_api_envelope([]))])
    _run(
        auto_api.fetch_offers(
            "autoscout24", fake, api_key="secret", country="de",
            filters={"brand": "BMW", "year_from": 2020, "price_from": 0, "ignored": "x"},
        )
    )
    req = fake.requests[0]
    assert req.method == "GET"
    assert req.url == "https://api1.auto-api.com/api/v2/autoscout24/offers"
    assert req.params["api_key"] == "secret"
    assert req.params["page"] == "1"
    assert req.params["brand"] == "BMW"
    assert req.params["year_from"] == "2020"
    assert "price_from" not in req.params  # 0 dropped (omitempty)
    assert "ignored" not in req.params  # not a documented filter key


def test_auto_api_paginates_until_next_page_zero():
    fake = FakeApi([
        _resp(_auto_api_envelope([_auto_api_offer(inner_id="P1", url="https://www.autoscout24.de/a/P1")], page=1, next_page=2)),
        _resp(_auto_api_envelope([_auto_api_offer(inner_id="P2", url="https://www.autoscout24.de/a/P2")], page=2, next_page=0)),
    ])
    pull = _run(auto_api.fetch_offers("autoscout24", fake, api_key="k", country="de"))
    assert pull.pages_fetched == 2 and pull.extracted == 2
    assert [r.source_listing_id for r in pull.records] == ["P1", "P2"]
    assert fake.requests[1].params["page"] == "2"


def test_auto_api_max_pages_caps_pagination():
    # next_page always advances; max_pages must stop the loop.
    def page_resp(req):
        p = int(req.params["page"])
        return _resp(_auto_api_envelope(
            [_auto_api_offer(inner_id=f"X{p}", url=f"https://www.autoscout24.de/a/X{p}")],
            page=p, next_page=p + 1,
        ))
    fake = FakeApi([page_resp] * 10)
    pull = _run(auto_api.fetch_offers("autoscout24", fake, api_key="k", country="de", max_pages=3))
    assert pull.pages_fetched == 3


def test_auto_api_skips_listing_missing_critical_field():
    bad = _auto_api_offer(inner_id="NOIMG", images=())  # no image → fails critical
    fake = FakeApi([_resp(_auto_api_envelope([bad, _auto_api_offer(inner_id="GOOD")]))])
    pull = _run(auto_api.fetch_offers("autoscout24", fake, api_key="k", country="de"))
    assert pull.seen == 2 and pull.extracted == 1
    ident, reason = pull.skipped[0]
    assert ident == "NOIMG"
    assert "missing_critical" in reason and "images" in reason


@pytest.mark.parametrize("status,exc", [
    (401, AggregatorAuthError),
    (403, AggregatorAuthError),
    (429, AggregatorRateLimited),
    (500, AggregatorError),
])
def test_auto_api_maps_http_errors(status, exc):
    fake = FakeApi([_resp({"message": "nope"}, status=status)])
    with pytest.raises(exc) as ei:
        _run(auto_api.fetch_offers("autoscout24", fake, api_key="k", country="de"))
    assert ei.value.status_code == status


def test_auto_api_rate_limit_reads_retry_after():
    fake = FakeApi([_resp({"message": "slow down"}, status=429, headers={"Retry-After": "30"})])
    with pytest.raises(AggregatorRateLimited) as ei:
        _run(auto_api.fetch_offers("autoscout24", fake, api_key="k", country="de"))
    assert ei.value.retry_after == 30


def test_auto_api_malformed_json_raises_aggregator_error():
    fake = FakeApi([_resp(b"<html>not json</html>")])
    with pytest.raises(AggregatorError):
        _run(auto_api.fetch_offers("autoscout24", fake, api_key="k", country="de"))


# ── carapis: key gating ───────────────────────────────────────────────────────
def test_carapis_missing_key_raises_before_network():
    fake = FakeApi(boom=True)
    with pytest.raises(MissingApiKeyError):
        _run(carapis.fetch_listings("lacentrale", fake, api_key="", country="fr"))
    assert fake.requests == []


# ── carapis: mapping ──────────────────────────────────────────────────────────
def test_carapis_maps_listing_to_record():
    fake = FakeApi([_resp(_carapis_envelope([_carapis_listing()]))])
    pull = _run(carapis.fetch_listings("lacentrale", fake, api_key="k", country="fr"))

    assert pull.extracted == 1
    rec = pull.records[0]
    assert rec.make == "Renault"
    assert rec.model == "Clio"
    assert rec.year == 2019
    assert rec.mileage_km == 60000
    assert rec.fuel_type is FuelType.GASOLINE  # fuel_type field
    assert rec.transmission is Transmission.MANUAL
    assert rec.price == Decimal("12990")
    assert rec.currency == "EUR"
    assert rec.images == ("https://img/c1.jpg",)  # mapped from `photos`
    assert rec.source_url == "https://www.lacentrale.fr/auto-1"
    assert rec.source_domain == "lacentrale.fr"
    assert rec.country == "FR"
    assert rec.source_listing_id == "1"


def test_carapis_request_shape_has_bearer_auth():
    fake = FakeApi([_resp(_carapis_envelope([]))])
    _run(carapis.fetch_listings("lacentrale", fake, api_key="sk_123", country="fr", limit=50))
    req = fake.requests[0]
    assert req.method == "GET"
    assert req.url == "https://api.carapis.com/v2/listings"
    assert req.params == {"source": "lacentrale", "limit": "50", "page": "1"}
    assert req.headers["Authorization"] == "Bearer sk_123"


def test_carapis_paginates_until_short_page():
    full = [_carapis_listing(lid=i, url=f"https://www.lacentrale.fr/auto-{i}") for i in range(2)]
    tail = [_carapis_listing(lid=99, url="https://www.lacentrale.fr/auto-99")]
    fake = FakeApi([
        _resp(_carapis_envelope(full, count=3, page=1, limit=2)),
        _resp(_carapis_envelope(tail, count=3, page=2, limit=2)),
    ])
    pull = _run(carapis.fetch_listings("lacentrale", fake, api_key="k", country="fr", limit=2))
    assert pull.pages_fetched == 2 and pull.extracted == 3
    assert fake.requests[1].params["page"] == "2"


def test_carapis_stops_when_count_reached():
    page = [_carapis_listing(lid=i, url=f"https://www.lacentrale.fr/auto-{i}") for i in range(2)]
    # Full page of `limit`, but count==2 already satisfied → must not fetch page 2.
    fake = FakeApi([_resp(_carapis_envelope(page, count=2, page=1, limit=2))])
    pull = _run(carapis.fetch_listings("lacentrale", fake, api_key="k", country="fr", limit=2))
    assert pull.pages_fetched == 1 and pull.extracted == 2


def test_carapis_skips_missing_critical():
    bad = _carapis_listing(lid=7, photos=())  # no image
    fake = FakeApi([_resp(_carapis_envelope([bad]))])
    pull = _run(carapis.fetch_listings("lacentrale", fake, api_key="k", country="fr"))
    assert pull.extracted == 0 and pull.seen == 1
    assert pull.skipped[0][0] == "7"
    assert "images" in pull.skipped[0][1]


@pytest.mark.parametrize("status,exc", [
    (401, AggregatorAuthError),
    (429, AggregatorRateLimited),
    (503, AggregatorError),
])
def test_carapis_maps_http_errors(status, exc):
    fake = FakeApi([_resp({"detail": "Invalid API key"}, status=status)])
    with pytest.raises(exc) as ei:
        _run(carapis.fetch_listings("lacentrale", fake, api_key="k", country="fr"))
    assert ei.value.status_code == status
