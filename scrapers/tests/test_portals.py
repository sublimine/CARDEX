"""
Portal scraper tests — BasePortalScraper orchestration + AutoScout24 primitives.

Two layers, mirroring the design:

  * BasePortalScraper.run() is the template method that owns every cross-cutting
    concern (tier/circuit/identity/pagination/soft-block/trust/sink). It is tested
    against a minimal `_FakeScraper` so orchestration is exercised in isolation
    from any portal's HTML or HTTP behaviour.
  * AutoScout24Scraper supplies the AS24-specific primitives (grid partition,
    fuel subdivision, URL building, Next.js JSON extraction, retry/softblock GET).
    Those are tested directly with a fake duck-typed session.

Coroutines are driven synchronously with asyncio.run() (engine convention). The
fake scrapers set SLEEP_BASE/JITTER to 0 so the jittered inter-page sleep is an
instant asyncio.sleep(0) — no monkeypatching of the base sleep needed.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from scrapers.engine.identity import store
from scrapers.engine.router import circuit
from scrapers.portals.base import BasePortalScraper, RunResult, RunStatus
from scrapers.portals.autoscout24_base import AutoScout24Scraper
from scrapers.portals.be import AutoScout24BE
from scrapers.portals.ch import AutoScout24CH
from scrapers.portals.de import AutoScout24DE
from scrapers.portals.es import AutoScout24ES
from scrapers.portals.fr import AutoScout24FR
from scrapers.portals.nl import AutoScout24NL

_AS24_DOMAIN = "autoscout24.de"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class _Resp:
    """Minimal duck-typed HTTP response (curl_cffi shape: .status_code, .text)."""

    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _Session:
    """Fake AsyncSession: yields queued responses (or raises queued exceptions)."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.urls: list[str] = []

    async def get(self, url: str, timeout: int | None = None) -> _Resp:
        self.urls.append(url)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _CollectSink:
    """Collecting sink that records streamed batches and whether finalize ran.

    Duck-types the production StreamingDeltaSink (callable + finalize), so it drives the
    exact on_urls/finalize contract BasePortalScraper.run uses live: URLs arrive in
    batches during the run, and finalize runs once, only on a complete clean cycle.
    """

    def __init__(self) -> None:
        self.urls: list[str] = []
        self.batches: int = 0
        self.finalized: bool = False

    async def __call__(self, urls: list[str]) -> None:
        self.batches += 1
        self.urls.extend(urls)

    async def finalize(self) -> None:
        self.finalized = True


class _FakeScraper(BasePortalScraper):
    """Programmable BasePortalScraper for exercising run() orchestration."""

    DOMAIN = _AS24_DOMAIN
    COUNTRY = "DE"
    PAGE_SIZE = 2
    MAX_PAGES = 3
    SLEEP_BASE = 0.0
    SLEEP_JITTER = 0.0

    def __init__(self, segments, page_fn, subdivider=None) -> None:
        self._segments = segments
        self._page_fn = page_fn
        self._subdivider = subdivider
        self.calls: list[tuple[dict, int]] = []

    def partition_params(self) -> list[dict]:
        return [dict(s) for s in self._segments]

    async def fetch_segment(self, session, params, page_num):
        self.calls.append((dict(params), page_num))
        return list(self._page_fn(params, page_num))

    def subdivide_segment(self, params):
        return self._subdivider(params) if self._subdivider else []


# --------------------------------------------------------------------------- #
# BasePortalScraper — validation
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_validate_requires_domain_and_country(conn) -> None:
    scraper = _FakeScraper([{"k": 1}], lambda p, n: [])
    scraper.DOMAIN = ""
    with pytest.raises(ValueError):
        _run(scraper.run(conn, None))


@pytest.mark.unit
def test_run_result_url_count() -> None:
    result = RunResult(RunStatus.OK, tier="T2", url_count=3)
    assert result.url_count == 3
    assert RunResult(RunStatus.OK, tier="T2").url_count == 0
    assert RunResult(RunStatus.OK, tier="T2").incomplete is False


# --------------------------------------------------------------------------- #
# BasePortalScraper.run() — circuit / identity gates
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_run_circuit_open_short_circuits(conn, active_identity) -> None:
    # Open both the baseline (T2) and the escalation ceiling (T3) so effective_tier
    # cannot escape upward — run() must then report CIRCUIT_OPEN.
    circuit.force_open(conn, _AS24_DOMAIN, "T2")
    circuit.force_open(conn, _AS24_DOMAIN, "T3")
    scraper = _FakeScraper([{"y": 1}], lambda p, n: ["/u/1"])

    result = _run(scraper.run(conn, _Session([])))

    assert result.status is RunStatus.CIRCUIT_OPEN
    assert result.tier == "T3"  # escalated to ceiling, still open
    assert scraper.calls == []  # never fetched


@pytest.mark.unit
def test_run_no_identity_when_pool_empty(conn) -> None:
    # No identity saved → pick_for_portal returns None → NO_IDENTITY.
    scraper = _FakeScraper([{"y": 1}], lambda p, n: ["/u/1"])

    result = _run(scraper.run(conn, _Session([])))

    assert result.status is RunStatus.NO_IDENTITY
    assert result.identity_id is None
    assert scraper.calls == []


# --------------------------------------------------------------------------- #
# BasePortalScraper.run() — happy path + sink + trust
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_run_ok_streams_urls_to_sink_finalizes_and_rewards_trust(conn, active_identity) -> None:
    seg = {"year": 2020}
    # Page 1 full, page 2 short (< PAGE_SIZE) → segment exhausts cleanly on a short page.
    scraper = _FakeScraper([seg], lambda p, n: ["/u/a", "/u/b"] if n == 1 else ["/u/c"])
    sink = _CollectSink()

    before = store.get(conn, active_identity.id).trust_score
    result = _run(scraper.run(conn, _Session([]), on_urls=sink))
    after = store.get(conn, active_identity.id).trust_score

    assert result.status is RunStatus.OK
    assert result.identity_id == active_identity.id
    assert sorted(sink.urls) == ["/u/a", "/u/b", "/u/c"]
    assert result.url_count == 3
    assert result.segments == 1
    assert result.incomplete is False
    assert sink.finalized is True  # clean cycle → stale reconciliation ran
    assert after == pytest.approx(before + 0.05)


@pytest.mark.unit
def test_run_ok_dedups_urls_across_pages_and_segments(conn, active_identity) -> None:
    # Page 1 full (2 fresh), page 2 repeats one + one new (still "full" raw len 2),
    # page 3 short → break. Across the two segments the same URL must appear once.
    def page_fn(params, n):
        if n == 1:
            return ["/u/1", "/u/2"]
        if n == 2:
            return ["/u/2", "/u/3"]  # /u/2 duplicate
        return ["/u/3"]  # short page (raw len 1 < PAGE_SIZE 2) → stop

    scraper = _FakeScraper([{"s": "a"}, {"s": "b"}], page_fn)
    sink = _CollectSink()
    result = _run(scraper.run(conn, _Session([]), on_urls=sink))

    assert result.status is RunStatus.OK
    assert sorted(sink.urls) == ["/u/1", "/u/2", "/u/3"]  # globally unique
    assert result.url_count == 3
    assert result.segments == 2


@pytest.mark.unit
def test_run_empty_harvest_is_empty_suspect_not_ok(conn, active_identity) -> None:
    # A single-segment portal that harvested ZERO deep links. It is NOT a soft block
    # (one empty cycle < the 3 ZeroUrlTracker needs), but it is ALSO not a clean
    # success: harvest-0 must demote to EMPTY_SUSPECT so the coordinator re-evaluates
    # it instead of marking it `done`, and trust stays neutral (no reward, no penalty).
    scraper = _FakeScraper([{"s": "a"}], lambda p, n: [])
    calls = {"n": 0}

    async def sink(urls):
        calls["n"] += 1

    before = store.get(conn, active_identity.id).trust_score
    result = _run(scraper.run(conn, _Session([]), on_urls=sink))
    after = store.get(conn, active_identity.id).trust_score

    assert result.status is RunStatus.EMPTY_SUSPECT
    assert result.url_count == 0
    assert calls["n"] == 0
    assert after == pytest.approx(before)  # neutral: no +0.05 reward, no -1.0 penalty


@pytest.mark.unit
def test_run_empty_harvest_skips_finalize(conn, active_identity) -> None:
    # The critical data-integrity guard: a zero harvest must NEVER run the stale GONE
    # delete, which would wipe the portal's entire existing index on a transient block.
    scraper = _FakeScraper([{"s": "a"}], lambda p, n: [])
    sink = _CollectSink()

    result = _run(scraper.run(conn, _Session([]), on_urls=sink))

    assert result.status is RunStatus.EMPTY_SUSPECT
    assert sink.urls == []
    assert sink.finalized is False  # harvest-0 → no stale delete, index preserved


# --------------------------------------------------------------------------- #
# BasePortalScraper.run() — soft block
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_run_soft_blocked_after_three_empty_segments(conn, active_identity) -> None:
    scraper = _FakeScraper([{"s": 1}, {"s": 2}, {"s": 3}, {"s": 4}], lambda p, n: [])

    before = store.get(conn, active_identity.id).trust_score
    result = _run(scraper.run(conn, _Session([])))
    after = store.get(conn, active_identity.id).trust_score

    assert result.status is RunStatus.SOFT_BLOCKED
    assert result.url_count == 0
    assert result.segments == 3  # aborted on the third empty cycle, 4th never run
    assert after == pytest.approx(before - 1.0)


# --------------------------------------------------------------------------- #
# BasePortalScraper.run() — page-cap subdivision (structural)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_run_subdivides_segment_on_page_ceiling(conn, active_identity) -> None:
    # Base segment fills all MAX_PAGES (3) with full pages (2 each) → ceiling hit.
    # Subdivision yields two sub-segments, each a single short page.
    def page_fn(params, n):
        if params.get("fuel"):
            return [f"/u/{params['fuel']}/{n}"]  # one url then short → break
        return [f"/u/base/{n}/0", f"/u/base/{n}/1"]  # full page every page

    def subdivider(params):
        return [{**params, "fuel": "P"}, {**params, "fuel": "D"}]

    scraper = _FakeScraper([{"y": 2020}], page_fn, subdivider=subdivider)
    sink = _CollectSink()
    result = _run(scraper.run(conn, _Session([]), on_urls=sink))

    assert result.status is RunStatus.OK
    # Base produced 3 full pages × 2 = 6 urls; each sub produced 1.
    base_urls = {f"/u/base/{n}/{i}" for n in (1, 2, 3) for i in (0, 1)}
    assert base_urls <= set(sink.urls)
    assert "/u/P/1" in sink.urls and "/u/D/1" in sink.urls
    # Base paginated to the ceiling (3 pages), each sub fetched exactly 1 page.
    base_calls = [c for c in scraper.calls if not c[0].get("fuel")]
    assert len(base_calls) == 3


@pytest.mark.unit
def test_run_no_subdivision_when_short_page(conn, active_identity) -> None:
    # Segment ends on a short page before the ceiling → subdivide_segment unused.
    subdiv_called = {"n": 0}

    def subdivider(params):
        subdiv_called["n"] += 1
        return [{**params, "fuel": "P"}]

    scraper = _FakeScraper([{"y": 2020}], lambda p, n: ["/u/x"], subdivider=subdivider)
    sink = _CollectSink()
    result = _run(scraper.run(conn, _Session([]), on_urls=sink))

    assert result.status is RunStatus.OK
    assert subdiv_called["n"] == 0
    assert sink.urls == ["/u/x"]
    assert result.url_count == 1


# --------------------------------------------------------------------------- #
# BasePortalScraper.run() — transient mid-segment truncation resilience
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_run_refetches_transient_empty_page_then_recovers(conn, active_identity) -> None:
    # A full page followed by an empty one mid-segment is a transient block, not the end
    # of inventory: the paginator re-fetches the empty page and continues instead of
    # truncating. (A real end is a SHORT page, handled separately.)
    calls = {"p2": 0}

    def page_fn(params, n):
        if n == 1:
            return ["/u/1", "/u/2"]  # full
        if n == 2:
            calls["p2"] += 1
            return [] if calls["p2"] == 1 else ["/u/3", "/u/4"]  # empty once, then recovers
        return ["/u/5"]  # short → clean end

    scraper = _FakeScraper([{"s": 1}], page_fn)
    sink = _CollectSink()
    result = _run(scraper.run(conn, _Session([]), on_urls=sink))

    assert result.status is RunStatus.OK
    assert result.incomplete is False
    assert sorted(sink.urls) == ["/u/1", "/u/2", "/u/3", "/u/4", "/u/5"]
    assert sink.finalized is True
    assert calls["p2"] == 2  # initial empty fetch + one refetch that recovered


@pytest.mark.unit
def test_run_incomplete_on_persistent_empty_skips_finalize(conn, active_identity) -> None:
    # A full page followed by a *persistently* empty page → suspected truncation: the
    # cycle persists what it found (status OK) but skips the stale GONE delete, so live
    # listings the scrape never reached are not wrongly removed. This is the autotrack
    # 220k→16.9k truncation in miniature, now contained.
    def page_fn(params, n):
        return ["/u/1", "/u/2"] if n == 1 else []  # full, then empty forever

    scraper = _FakeScraper([{"s": 1}], page_fn)
    sink = _CollectSink()
    result = _run(scraper.run(conn, _Session([]), on_urls=sink))

    assert result.status is RunStatus.OK
    assert result.incomplete is True
    assert sorted(sink.urls) == ["/u/1", "/u/2"]
    assert sink.finalized is False  # transient truncation → no stale delete


# --------------------------------------------------------------------------- #
# AutoScout24Scraper — partition / subdivision
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_as24_partition_is_year_bands_times_price_ceilings() -> None:
    scraper = AutoScout24DE()
    segments = scraper.partition_params()
    assert len(segments) == len(scraper.YEAR_BANDS) * len(scraper.PRICE_CEILINGS)
    assert all(s["fuel"] == "" for s in segments)
    # Segments are unique (year_from, year_to, price_to) triples.
    keys = {(s["year_from"], s["year_to"], s["price_to"]) for s in segments}
    assert len(keys) == len(segments)


@pytest.mark.unit
def test_as24_subdivide_by_fuel_then_stops() -> None:
    scraper = AutoScout24DE()
    subs = scraper.subdivide_segment({"year_from": 2018, "year_to": 2020, "price_to": None, "fuel": ""})
    assert [s["fuel"] for s in subs] == list(scraper.FUELS)
    # A fuel-split segment cannot be subdivided further.
    assert scraper.subdivide_segment({"fuel": "P"}) == []


# --------------------------------------------------------------------------- #
# AutoScout24Scraper — URL building
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_as24_build_url_full() -> None:
    url = AutoScout24DE()._build_url(
        {"year_from": 2018, "year_to": 2020, "price_to": 20000, "fuel": "D"}, 3
    )
    assert url == (
        "https://www.autoscout24.de/lst?atype=C&desc=0&sort=standard"
        "&year_from=2018&year_to=2020&page=3&price_to=20000&fuel=D"
    )


@pytest.mark.unit
def test_as24_build_url_omits_price_when_none_and_fuel_when_empty() -> None:
    url = AutoScout24DE()._build_url(
        {"year_from": 1990, "year_to": 2000, "price_to": None, "fuel": ""}, 1
    )
    assert "price_to" not in url
    assert "fuel" not in url
    assert url.endswith("&year_from=1990&year_to=2000&page=1")


# --------------------------------------------------------------------------- #
# AutoScout24Scraper — extraction
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_as24_extract_pulls_prefixed_listings_and_dedups() -> None:
    html = (
        '{"id":1,"url":"/angebote/bmw-320d-abc123","price":15000}'
        '{"url":"/angebote/audi-a4-def456"}'
        '{"url":"/angebote/bmw-320d-abc123"}'   # duplicate
        '{"url":"/haendler/some-dealer"}'        # wrong prefix → ignored
    )
    urls = AutoScout24DE()._extract(html)
    assert urls == [
        "https://www.autoscout24.de/angebote/bmw-320d-abc123",
        "https://www.autoscout24.de/angebote/audi-a4-def456",
    ]


@pytest.mark.unit
def test_as24_extract_handles_bilingual_prefixes() -> None:
    html = '{"url":"/annonces/peugeot-208-x"}{"url":"/aanbod/vw-golf-y"}'
    urls = AutoScout24BE()._extract(html)
    assert urls == [
        "https://www.autoscout24.be/annonces/peugeot-208-x",
        "https://www.autoscout24.be/aanbod/vw-golf-y",
    ]


@pytest.mark.unit
def test_as24_extract_empty_when_no_match() -> None:
    assert AutoScout24DE()._extract('{"url":"/haendler/x"}no listings here') == []


# --------------------------------------------------------------------------- #
# AutoScout24Scraper — fetch_segment (retry / softblock / status)
# --------------------------------------------------------------------------- #
def _no_backoff(scraper: AutoScout24Scraper) -> None:
    async def _noop(attempt: int, factor: float = 1.0) -> None:
        return None

    scraper._retry_backoff = _noop  # type: ignore[method-assign]


@pytest.mark.unit
def test_as24_fetch_segment_extracts_on_200() -> None:
    scraper = AutoScout24DE()
    html = '{"url":"/angebote/a-1"}{"url":"/angebote/b-2"}'
    session = _Session([_Resp(200, html)])
    urls = _run(scraper.fetch_segment(session, {"year_from": 2020, "year_to": 2022, "price_to": None, "fuel": ""}, 1))
    assert urls == [
        "https://www.autoscout24.de/angebote/a-1",
        "https://www.autoscout24.de/angebote/b-2",
    ]
    assert len(session.urls) == 1


@pytest.mark.unit
def test_as24_fetch_segment_retries_block_status_then_gives_up() -> None:
    scraper = AutoScout24DE()
    _no_backoff(scraper)
    session = _Session([_Resp(403), _Resp(429), _Resp(503)])
    urls = _run(scraper.fetch_segment(session, {"year_from": 2020, "year_to": 2022, "price_to": None, "fuel": ""}, 1))
    assert urls == []
    assert len(session.urls) == scraper.RETRY_ATTEMPTS  # exhausted all attempts


@pytest.mark.unit
def test_as24_fetch_segment_recovers_after_block() -> None:
    scraper = AutoScout24DE()
    _no_backoff(scraper)
    html = '{"url":"/angebote/ok-9"}'
    session = _Session([_Resp(403), _Resp(200, html)])
    urls = _run(scraper.fetch_segment(session, {"year_from": 2020, "year_to": 2022, "price_to": None, "fuel": ""}, 1))
    assert urls == ["https://www.autoscout24.de/angebote/ok-9"]
    assert len(session.urls) == 2


@pytest.mark.unit
def test_as24_fetch_segment_retries_softblock_200() -> None:
    scraper = AutoScout24DE()
    _no_backoff(scraper)
    challenge = "<html><title>Just a moment...</title>checking your browser</html>"
    session = _Session([_Resp(200, challenge), _Resp(200, challenge), _Resp(200, challenge)])
    urls = _run(scraper.fetch_segment(session, {"year_from": 2020, "year_to": 2022, "price_to": None, "fuel": ""}, 1))
    assert urls == []
    assert len(session.urls) == scraper.RETRY_ATTEMPTS


@pytest.mark.unit
def test_as24_fetch_segment_non_block_status_returns_empty_no_retry() -> None:
    scraper = AutoScout24DE()
    session = _Session([_Resp(404)])
    urls = _run(scraper.fetch_segment(session, {"year_from": 2020, "year_to": 2022, "price_to": None, "fuel": ""}, 1))
    assert urls == []
    assert len(session.urls) == 1  # 404 is not retried


@pytest.mark.unit
def test_as24_fetch_segment_retries_transport_error() -> None:
    scraper = AutoScout24DE()
    _no_backoff(scraper)
    session = _Session([ConnectionError("reset"), ConnectionError("reset"), _Resp(200, '{"url":"/angebote/z-0"}')])
    urls = _run(scraper.fetch_segment(session, {"year_from": 2020, "year_to": 2022, "price_to": None, "fuel": ""}, 1))
    assert urls == ["https://www.autoscout24.de/angebote/z-0"]
    assert len(session.urls) == 3


@pytest.mark.unit
def test_as24_validate_requires_host_and_prefixes(conn) -> None:
    class _Broken(AutoScout24Scraper):
        DOMAIN = "autoscout24.de"
        COUNTRY = "DE"
        # HOST / LISTING_PREFIXES left unset

    with pytest.raises(ValueError):
        _run(_Broken().run(conn, _Session([])))


# --------------------------------------------------------------------------- #
# country variants
# --------------------------------------------------------------------------- #
@pytest.mark.unit
@pytest.mark.parametrize(
    "cls, domain, country, host, prefixes",
    [
        (AutoScout24DE, "autoscout24.de", "DE", "www.autoscout24.de", ("/angebote/",)),
        (AutoScout24FR, "autoscout24.fr", "FR", "www.autoscout24.fr", ("/annonces/",)),
        (AutoScout24ES, "autoscout24.es", "ES", "www.autoscout24.es", ("/anuncios/",)),
        (AutoScout24NL, "autoscout24.nl", "NL", "www.autoscout24.nl", ("/aanbod/",)),
        (AutoScout24BE, "autoscout24.be", "BE", "www.autoscout24.be", ("/annonces/", "/aanbod/")),
        (AutoScout24CH, "autoscout24.ch", "CH", "www.autoscout24.ch", ("/annonces/", "/angebote/")),
    ],
)
def test_country_variant_config(cls, domain, country, host, prefixes) -> None:
    scraper = cls()
    assert scraper.DOMAIN == domain
    assert scraper.COUNTRY == country
    assert scraper.HOST == host
    assert scraper.LISTING_PREFIXES == prefixes
    scraper._validate()  # must not raise


@pytest.mark.unit
def test_all_country_variants_resolve_to_tier_t2(conn) -> None:
    from scrapers.engine.router.domain_map import Tier

    for cls in (AutoScout24DE, AutoScout24FR, AutoScout24ES, AutoScout24NL, AutoScout24BE, AutoScout24CH):
        scraper = cls()
        assert scraper._select_tier(conn) is Tier.T2
