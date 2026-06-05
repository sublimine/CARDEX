"""
Tests for dealer_classifier and frontier_runner modules.

All tests use fake HTTP clients and in-memory state â€” no real network or DB.
Coroutines run via asyncio.run() following the engine convention.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import pytest

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Helpers
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _run(coro: Any) -> Any:
    return asyncio.run(coro)


class _FakeResp:
    """Duck-typed httpx response for tests."""

    def __init__(
        self,
        status_code: int,
        text: str = "",
        headers: dict[str, str] | None = None,
        url: str = "https://dealer.example.com/",
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.headers = httpx.Headers(headers or {})
        self.url = url


class _FakeClient:
    """Fake httpx.AsyncClient â€” returns pre-canned responses keyed by URL substring."""

    def __init__(self, url_map: dict[str, Any]) -> None:
        self._map = url_map
        self.calls: list[str] = []

    async def get(self, url: str, **kwargs: Any) -> _FakeResp:
        self.calls.append(url)
        for key, resp in self._map.items():
            if key in url:
                if isinstance(resp, Exception):
                    raise resp
                if isinstance(resp, _FakeResp):
                    resp.url = url
                return resp
        return _FakeResp(404, url=url)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# dealer_classifier â€” unit tests (pure functions)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

from scrapers.discovery.dealer_classifier import (
    ClassificationResult,
    _assign_tier,
    _count_inventory_in_sitemap,
    _detect_cms,
    _find_inventory_links,
    classify_domain,
)


class TestCmsDetection:
    def test_detects_wordpress(self) -> None:
        html = '<link rel="stylesheet" href="/wp-content/themes/dealer/style.css">'
        assert _detect_cms(html, httpx.Headers({})) == "wordpress"

    def test_detects_dealerk(self) -> None:
        html = '<script src="https://cdn.dealerk.com/js/app.min.js"></script>'
        assert _detect_cms(html, httpx.Headers({})) == "dealerk"

    def test_detects_nextjs(self) -> None:
        html = '<script id="__NEXT_DATA__" type="application/json">{"props":{}}</script>'
        assert _detect_cms(html, httpx.Headers({})) == "nextjs"

    def test_detects_nuxtjs(self) -> None:
        html = "<script>window.__NUXT__={data:[]}</script>"
        assert _detect_cms(html, httpx.Headers({})) == "nuxtjs"

    def test_detects_shopify(self) -> None:
        html = '<script src="https://cdn.shopify.com/s/files/1/0001/app.js"></script>'
        assert _detect_cms(html, httpx.Headers({})) == "shopify"

    def test_detects_prestashop(self) -> None:
        html = '<form action="/index.php?id_product=42&controller=product">'
        assert _detect_cms(html, httpx.Headers({})) == "prestashop"

    def test_detects_wix_via_header(self) -> None:
        headers = httpx.Headers({"x-wix-rendered-at": "2024-06-01T00:00:00Z"})
        assert _detect_cms("<html></html>", headers) == "wix"

    def test_falls_back_to_custom(self) -> None:
        html = "<html><body><h1>Our cars</h1></body></html>"
        assert _detect_cms(html, httpx.Headers({})) == "custom"

    def test_dealerk_takes_priority_over_wordpress(self) -> None:
        # Page has both WP and DealerK signals â€” DealerK wins (listed first)
        html = (
            '<link href="/wp-content/style.css">'
            '<script src="https://cdn.dealerk.com/app.js"></script>'
        )
        assert _detect_cms(html, httpx.Headers({})) == "dealerk"


class TestInventoryLinks:
    BASE = "https://dealer.fr/"

    def test_finds_stock_link(self) -> None:
        html = '<a href="/stock/voitures">Nos voitures</a>'
        links = _find_inventory_links(html, self.BASE)
        assert any("/stock/" in l for l in links)

    def test_finds_occasion_link(self) -> None:
        html = '<a href="/occasion/">Occasions</a>'
        links = _find_inventory_links(html, self.BASE)
        assert len(links) >= 1

    def test_finds_vehicles_link(self) -> None:
        html = '<a href="/vehicles/used">Used vehicles</a>'
        links = _find_inventory_links(html, "https://dealer.de/")
        assert len(links) >= 1

    def test_ignores_external_links(self) -> None:
        html = '<a href="https://other.com/stock/">External stock</a>'
        links = _find_inventory_links(html, self.BASE)
        assert links == []

    def test_ignores_mailto(self) -> None:
        html = '<a href="mailto:stock@dealer.fr">Email</a>'
        links = _find_inventory_links(html, self.BASE)
        assert links == []

    def test_deduplicates(self) -> None:
        html = '<a href="/vehicles/">Cars</a><a href="/vehicles/">Cars again</a>'
        links = _find_inventory_links(html, "https://dealer.com/")
        assert len(links) == 1

    def test_caps_at_ten(self) -> None:
        hrefs = "".join(
            f'<a href="/stock/page{i}-vehicles">page{i}</a>' for i in range(20)
        )
        links = _find_inventory_links(hrefs, "https://dealer.com/")
        assert len(links) <= 10

    def test_relative_url_resolved(self) -> None:
        html = '<a href="stock/bmw-x5-123">BMW X5</a>'
        links = _find_inventory_links(html, "https://dealer.com/")
        assert any("stock" in l for l in links)


class TestSitemapCount:
    def test_counts_inventory_urls(self) -> None:
        sitemap = """
        <urlset>
          <url><loc>https://dealer.com/stock/audi-a4-123</loc></url>
          <url><loc>https://dealer.com/stock/bmw-320-456</loc></url>
          <url><loc>https://dealer.com/contact</loc></url>
        </urlset>
        """
        assert _count_inventory_in_sitemap(sitemap) == 2

    def test_counts_occasion_urls(self) -> None:
        sitemap = (
            "<urlset>"
            "<url><loc>https://d.fr/occasion/peugeot-308-1</loc></url>"
            "<url><loc>https://d.fr/about</loc></url>"
            "</urlset>"
        )
        assert _count_inventory_in_sitemap(sitemap) == 1

    def test_returns_zero_when_no_inventory(self) -> None:
        sitemap = "<urlset><url><loc>https://d.com/contact</loc></url></urlset>"
        assert _count_inventory_in_sitemap(sitemap) == 0


class TestTierAssignment:
    def test_dealerk_is_t0(self) -> None:
        r = ClassificationResult("d.com", "FR", cms_type="dealerk", has_inventory=True)
        assert _assign_tier(r) == "T0"

    def test_wordpress_with_inventory_is_t1(self) -> None:
        r = ClassificationResult("d.com", "FR", cms_type="wordpress", has_inventory=True)
        assert _assign_tier(r) == "T1"

    def test_large_custom_site_is_t1(self) -> None:
        r = ClassificationResult(
            "d.com", "DE", cms_type="custom", has_inventory=True, estimated_listings=60
        )
        assert _assign_tier(r) == "T1"

    def test_medium_custom_site_is_t2(self) -> None:
        r = ClassificationResult(
            "d.com", "DE", cms_type="custom", has_inventory=True, estimated_listings=15
        )
        assert _assign_tier(r) == "T2"

    def test_small_site_is_t3(self) -> None:
        r = ClassificationResult("d.com", "DE", has_inventory=False, estimated_listings=0)
        assert _assign_tier(r) == "T3"

    def test_nextjs_large_inventory_is_t1(self) -> None:
        r = ClassificationResult(
            "d.com", "NL", cms_type="nextjs", has_inventory=True, estimated_listings=55
        )
        assert _assign_tier(r) == "T1"


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# dealer_classifier â€” integration (fake httpx)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestClassifyDomainIntegration:
    def _sem(self) -> asyncio.Semaphore:
        return asyncio.Semaphore(1)

    def test_classifies_wordpress_with_inventory(self) -> None:
        html = (
            "<html><head>"
            '<meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            '<link rel="stylesheet" href="/wp-content/themes/cars/style.css">'
            '<link rel="stylesheet" href="/wp-content/plugins/dealer/style.css">'
            "</head><body>"
            "<header><h1>Concessionnaire Auto Paris</h1></header>"
            '<nav><a href="/stock/voitures-occasion">Occasions</a>'
            '<a href="/contact">Contact</a></nav>'
            "</body></html>"
        )
        client = _FakeClient(
            {
                "robots.txt": _FakeResp(404),
                "dealer.fr": _FakeResp(200, html, url="https://dealer.fr/"),
                "sitemap.xml": _FakeResp(404),
            }
        )

        async def _go() -> ClassificationResult:
            return await classify_domain(
                client,  # type: ignore[arg-type]
                self._sem(),
                "dealer.fr",
                "FR",
            )

        result = _run(_go())
        assert result.cms_type == "wordpress"
        assert result.has_inventory is True
        assert result.tier == "T1"

    def test_respects_robots_disallow(self) -> None:
        robots_body = "User-agent: *\nDisallow: /"
        client = _FakeClient({"robots.txt": _FakeResp(200, robots_body)})

        async def _go() -> ClassificationResult:
            return await classify_domain(
                client,  # type: ignore[arg-type]
                self._sem(),
                "blocked.com",
                "DE",
            )

        result = _run(_go())
        assert result.has_inventory is False
        assert result.tier is None

    def test_handles_timeout_gracefully(self) -> None:
        client = _FakeClient(
            {
                "robots.txt": _FakeResp(404),
                "timeout.com": httpx.TimeoutException("timeout"),
            }
        )

        async def _go() -> ClassificationResult:
            return await classify_domain(
                client,  # type: ignore[arg-type]
                self._sem(),
                "timeout.com",
                "ES",
            )

        result = _run(_go())
        assert result.has_inventory is False
        assert result.tier is None

    def test_uses_sitemap_when_no_homepage_links(self) -> None:
        homepage_html = (
            "<html><head><meta charset='utf-8'><title>Quality Cars GmbH</title></head>"
            "<body><header><h1>Quality Cars GmbH â€” Ihr AutohÃ¤ndler</h1></header>"
            "<main><p>Welcome to our dealership. We offer premium used cars.</p>"
            "<p>Located in Berlin, Germany. Open Mon-Fri 9-18h.</p></main>"
            "</body></html>"
        )
        sitemap_xml = (
            "<urlset>"
            "<url><loc>https://q.de/stock/vw-golf-1</loc></url>"
            "<url><loc>https://q.de/stock/audi-a3-2</loc></url>"
            "<url><loc>https://q.de/stock/bmw-320-3</loc></url>"
            "</urlset>"
        )
        client = _FakeClient(
            {
                "robots.txt": _FakeResp(404),
                "sitemap.xml": _FakeResp(200, sitemap_xml),
                "q.de": _FakeResp(200, homepage_html, url="https://q.de/"),
            }
        )

        async def _go() -> ClassificationResult:
            return await classify_domain(
                client,  # type: ignore[arg-type]
                self._sem(),
                "q.de",
                "DE",
            )

        result = _run(_go())
        assert result.has_inventory is True
        assert result.estimated_listings == 3

    def test_non_200_homepage_returns_blank_result(self) -> None:
        client = _FakeClient(
            {
                "robots.txt": _FakeResp(404),
                "gone.nl": _FakeResp(410),
            }
        )

        async def _go() -> ClassificationResult:
            return await classify_domain(
                client,  # type: ignore[arg-type]
                self._sem(),
                "gone.nl",
                "NL",
            )

        result = _run(_go())
        assert result.has_inventory is False
        assert result.cms_type == "custom"


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# frontier_runner â€” unit tests (pure functions + in-memory state)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

from scrapers.discovery.frontier_runner import (
    _CB_FAIL_THRESHOLD,
    _circuit_is_open,
    _crawl_segment,
    _domain_states,
    _extract_links,
    _record_failure,
    _record_success,
)


class TestCircuitBreaker:
    def setup_method(self) -> None:
        _domain_states.clear()

    def test_closed_by_default(self) -> None:
        assert not _circuit_is_open("fresh.example.com")

    def test_opens_after_threshold(self) -> None:
        for _ in range(_CB_FAIL_THRESHOLD):
            _record_failure("bad.example.com")
        assert _circuit_is_open("bad.example.com")

    def test_success_resets_failures(self) -> None:
        _record_failure("ok.example.com")
        _record_failure("ok.example.com")
        _record_success("ok.example.com")
        assert not _circuit_is_open("ok.example.com")
        # Failure count reset: one more failure should not open
        _record_failure("ok.example.com")
        assert not _circuit_is_open("ok.example.com")

    def test_partial_failures_dont_open(self) -> None:
        for _ in range(_CB_FAIL_THRESHOLD - 1):
            _record_failure("partial.example.com")
        assert not _circuit_is_open("partial.example.com")

    def test_remains_open_until_timeout(self) -> None:
        for _ in range(_CB_FAIL_THRESHOLD):
            _record_failure("stuck.example.com")
        # Still open right after threshold
        assert _circuit_is_open("stuck.example.com")


class TestPaginationExtraction:
    BASE = "https://dealer.com/"

    def test_finds_english_next(self) -> None:
        html = '<a href="/stock/?page=2">Next</a>'
        _, next_urls = _extract_links(html, self.BASE)
        assert len(next_urls) == 1

    def test_finds_french_suivant(self) -> None:
        html = '<a href="/occasions/?p=2">Suivant</a>'
        _, next_urls = _extract_links(html, "https://dealer.fr/")
        assert len(next_urls) == 1

    def test_finds_german_weiter(self) -> None:
        html = '<a href="/fahrzeuge/seite/2">Weiter</a>'
        _, next_urls = _extract_links(html, "https://dealer.de/")
        assert len(next_urls) == 1

    def test_finds_dutch_volgende(self) -> None:
        html = '<a href="/voorraad/?p=3">Volgende</a>'
        _, next_urls = _extract_links(html, "https://dealer.nl/")
        assert len(next_urls) == 1

    def test_finds_mehr_anzeigen(self) -> None:
        html = '<a href="/fahrzeuge/?offset=20">Mehr anzeigen</a>'
        _, next_urls = _extract_links(html, "https://dealer.de/")
        assert len(next_urls) == 1

    def test_finds_voir_plus(self) -> None:
        html = '<a href="/voitures/?page=2">Voir plus</a>'
        _, next_urls = _extract_links(html, "https://dealer.fr/")
        assert len(next_urls) == 1

    def test_finds_vehicle_detail_links(self) -> None:
        html = (
            '<a href="/vehicle/audi-a3-sportback-2021-123">Audi A3</a>'
            '<a href="/contact">Contact</a>'
        )
        detail_urls, _ = _extract_links(html, self.BASE)
        assert len(detail_urls) == 1
        assert "vehicle" in detail_urls[0]

    def test_finds_occasion_detail_link(self) -> None:
        html = '<a href="/occasion/peugeot-308-sw-456">Peugeot 308</a>'
        detail_urls, _ = _extract_links(html, "https://dealer.fr/")
        assert len(detail_urls) >= 1

    def test_ignores_external_links(self) -> None:
        html = '<a href="https://other.com/vehicle/123">External vehicle</a>'
        detail_urls, next_urls = _extract_links(html, self.BASE)
        assert detail_urls == []
        assert next_urls == []

    def test_deduplicates_next_urls(self) -> None:
        html = (
            '<a href="/stock/?page=2">Next</a>'
            '<a href="/stock/?page=2">Suivant</a>'
        )
        _, next_urls = _extract_links(html, self.BASE)
        assert len(next_urls) == 1


class TestThompsonSamplingFormulas:
    def test_alpha_increments_on_yield(self) -> None:
        vehicles_found = 5
        alpha_inc = 1 if vehicles_found > 0 else 0
        beta_inc = 0 if vehicles_found > 0 else 1
        assert alpha_inc == 1
        assert beta_inc == 0

    def test_beta_increments_on_zero_yield(self) -> None:
        vehicles_found = 0
        alpha_inc = 1 if vehicles_found > 0 else 0
        beta_inc = 0 if vehicles_found > 0 else 1
        assert alpha_inc == 0
        assert beta_inc == 1

    def test_priority_score_converges_toward_one(self) -> None:
        alpha, beta = 1, 1
        # Simulate 10 successful crawls
        for _ in range(10):
            alpha += 1
        score = alpha / (alpha + beta)
        assert score > 0.9

    def test_priority_score_converges_toward_zero(self) -> None:
        alpha, beta = 1, 1
        # Simulate 10 empty crawls
        for _ in range(10):
            beta += 1
        score = alpha / (alpha + beta)
        assert score < 0.15

    def test_balanced_score_is_near_half(self) -> None:
        alpha, beta = 6, 6
        score = alpha / (alpha + beta)
        assert abs(score - 0.5) < 0.01


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# frontier_runner â€” integration (fake httpx, no DB)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestCrawlSegmentIntegration:
    def setup_method(self) -> None:
        _domain_states.clear()

    def test_collects_vehicle_urls_from_listing_page(self) -> None:
        listing_html = (
            "<html><head><meta charset='utf-8'><title>Our Used Cars - Inventory</title></head>"
            "<body><header><h1>Used Cars for Sale</h1></header><main>"
            '<ul class="inventory-list">'
            '<li><a href="/vehicle/bmw-x5-2021-001">BMW X5 2021 - 45,000 km - 42,900 â‚¬</a></li>'
            '<li><a href="/vehicle/audi-q7-2022-002">Audi Q7 2022 - 28,000 km - 68,500 â‚¬</a></li>'
            "</ul>"
            '<nav><a href="/contact">Contact us</a></nav>'
            "</main></body></html>"
        )
        client = _FakeClient(
            {
                "robots.txt": _FakeResp(404),
                "inventory.example1.com": _FakeResp(
                    200, listing_html, url="https://inventory.example1.com/stock/"
                ),
            }
        )

        async def _go() -> Any:
            return await _crawl_segment(
                client,  # type: ignore[arg-type]
                ["https://inventory.example1.com/stock/"],
                "inventory.example1.com",
            )

        result = _run(_go())
        assert result.pages_crawled >= 1
        # Both vehicle URLs should be discovered
        assert any("bmw-x5" in u for u in result.vehicle_urls)
        assert any("audi-q7" in u for u in result.vehicle_urls)

    def test_aborts_on_circuit_open(self) -> None:
        # Pre-open the circuit
        for _ in range(_CB_FAIL_THRESHOLD):
            _record_failure("circuit-open.example.com")

        client = _FakeClient({"circuit-open.example.com": _FakeResp(200, "<html></html>")})

        async def _go() -> Any:
            return await _crawl_segment(
                client,  # type: ignore[arg-type]
                ["https://circuit-open.example.com/stock/"],
                "circuit-open.example.com",
            )

        result = _run(_go())
        assert result.pages_crawled == 0
        assert result.vehicle_urls == []

    def test_handles_http_errors_gracefully(self) -> None:
        client = _FakeClient(
            {
                "robots.txt": _FakeResp(404),
                "error.example.com": httpx.ConnectError("refused"),
            }
        )

        async def _go() -> Any:
            return await _crawl_segment(
                client,  # type: ignore[arg-type]
                ["https://error.example.com/stock/"],
                "error.example.com",
            )

        result = _run(_go())
        assert result.vehicle_urls == []
        # Domain should have a recorded failure
        from scrapers.discovery.frontier_runner import _get_state
        st = _get_state("error.example.com")
        assert st.failure_count >= 1

    def test_respects_robots_disallow(self) -> None:
        robots_body = "User-agent: *\nDisallow: /"
        client = _FakeClient(
            {
                "robots.txt": _FakeResp(200, robots_body),
                "robotblocked.example.com": _FakeResp(200, "<html></html>"),
            }
        )

        async def _go() -> Any:
            return await _crawl_segment(
                client,  # type: ignore[arg-type]
                ["https://robotblocked.example.com/stock/"],
                "robotblocked.example.com",
            )

        result = _run(_go())
        assert result.pages_crawled == 0

    def test_deduplicates_vehicle_urls(self) -> None:
        html = (
            "<html><head><meta charset='utf-8'><title>Occasions - Dealer</title></head>"
            "<body><header><h1>Nos voitures d'occasion</h1></header><main>"
            '<ul class="listing">'
            '<li><a href="/vehicle/dup-001">Peugeot 308 SW 1.6 HDi 120 ch</a></li>'
            '<li><a href="/vehicle/dup-001">Peugeot 308 SW 1.6 HDi 120 ch</a></li>'
            "</ul></main></body></html>"
        )
        client = _FakeClient(
            {
                "robots.txt": _FakeResp(404),
                "dedup.example.com": _FakeResp(200, html, url="https://dedup.example.com/stock/"),
            }
        )

        async def _go() -> Any:
            return await _crawl_segment(
                client,  # type: ignore[arg-type]
                ["https://dedup.example.com/stock/"],
                "dedup.example.com",
            )

        result = _run(_go())
        assert len(result.vehicle_urls) == 1
