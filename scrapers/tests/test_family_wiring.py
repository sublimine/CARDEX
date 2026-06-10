"""
Family-recipe wiring — the CMS multiplier ACTIVATED in the dealer harvest flow.

Covers the additive routing extension (detector → harvester resolution):
  * a dealer whose homepage fingerprints a family with HIGH confidence resolves to
    the INSTANTIATED family recipe (endpoints filled with its host), NOT to the
    per-dealer ``build_config`` — and nothing is persisted (resolve-time view),
  * a dealer with no recognizable CMS takes today's per-dealer route untouched,
  * a family with ``min_confidence='high'`` REJECTS a 'medium' verdict (floor),
  * ``detect_web_type`` keeps its pre-family contract byte-for-byte when no family
    is involved (new ``cms``/``cms_confidence`` fields default to ""),
  * the cms signal alone (no family file) changes NOTHING — opt-in proven,
  * ``harvest_dealer`` runs end-to-end on a family-resolved dealer.

All in-memory MapFetcher fakes + tmp-dir stores — no network, no Redis, no Postgres.
"""
from __future__ import annotations

import asyncio

import pytest

from scrapers.dealer_scraping.detector import DetectionResult, detect_web_type
from scrapers.dealer_scraping.harvester import harvest_dealer, resolve_or_detect_config
from scrapers.pipeline.generic_extractor import FetchResult
from scrapers.portals import config as cfgmod
from scrapers.portals.config import FamilyEndpoints, FamilyMatch, FamilyRecipe


# ── in-memory transport (repo convention, mirrors test_dealer_harvester) ────────
class MapFetcher:
    def __init__(self, pages: dict[str, tuple[int, bytes]]):
        self._pages = pages
        self.requested: list[str] = []

    async def __call__(self, url: str) -> FetchResult:
        self.requested.append(url)
        if url in self._pages:
            status, body = self._pages[url]
            return FetchResult(url=url, status_code=status, body=body)
        return FetchResult(url=url, status_code=404, body=b"")


def _b(text: str) -> bytes:
    return text.encode("utf-8")


def _run(coro):
    return asyncio.run(coro)


_PAD = "<div class='spec'><span></span></div>" * 600


def _jsonld(make="BMW", model="320d", price="24900") -> bytes:
    return _b(
        "<html><head><script type=\"application/ld+json\">"
        '{"@context":"https://schema.org","@type":"Car",'
        f'"brand":{{"name":"{make}"}},"model":"{model}","vehicleModelDate":"2019",'
        '"mileageFromOdometer":{"value":"85000"},"image":["https://cdn.d.example/1.jpg"],'
        f'"offers":{{"price":"{price}","priceCurrency":"EUR"}}}}'
        "</script></head><body>" + _PAD + "</body></html>"
    )


# Two DISTINCT WordPress markers (/wp-content/ + /wp-json/) → confidence 'high'.
_WP_HOME_HIGH = _b(
    "<html><head>"
    '<link rel="stylesheet" href="/wp-content/themes/garage/style.css">'
    '<link rel="https://api.w.org/" href="https://wp-garage.de/wp-json/">'
    "</head><body>Willkommen bei WP Garage</body></html>"
)

# Exactly ONE WordPress marker (/wp-content/ only) → confidence 'medium'.
_WP_HOME_MEDIUM = _b(
    "<html><head>"
    '<link rel="stylesheet" href="/wp-content/themes/garage/style.css">'
    "</head><body>Willkommen</body></html>"
)


def _sitemap_pages(domain: str, home: bytes | None = None) -> dict[str, tuple[int, bytes]]:
    """A static dealer that yields via sitemap → the per-dealer probe SUCCEEDS, so a
    family resolution proves the shortcut beats build_config, not that it papered
    over a failed probe."""
    base = f"https://{domain}"
    sm = (
        "<urlset>"
        f"<url><loc>{base}/vehicles/bmw-320d-1</loc></url>"
        f"<url><loc>{base}/vehicles/audi-a4-2</loc></url>"
        "</urlset>"
    )
    pages = {
        f"{base}/robots.txt": (200, _b(f"Sitemap: {base}/sitemap.xml")),
        f"{base}/sitemap.xml": (200, _b(sm)),
        f"{base}/vehicles/bmw-320d-1": (200, _jsonld()),
        f"{base}/vehicles/audi-a4-2": (200, _jsonld(make="Audi", model="A4")),
    }
    if home is not None:
        pages[base] = (200, home)
    return pages


def _wordpress_family(min_confidence: str = "high") -> FamilyRecipe:
    return FamilyRecipe(
        family_key="wordpress",
        strategy="wp_rest",
        matches=FamilyMatch(cms="wordpress", min_confidence=min_confidence),
        endpoints=FamilyEndpoints(sitemap_hint="/wp-sitemap.xml", api_path_hint="/wp-json/wp/v2"),
    )


@pytest.fixture()
def isolated_stores(tmp_path, monkeypatch):
    """Point ALL THREE config stores at empty tmp dirs — tests never touch the repo's
    curated portals, generated dealers, or git-tracked families."""
    portal_dir = tmp_path / "portals"
    dealer_dir = tmp_path / "dealers"
    family_dir = tmp_path / "families"
    portal_dir.mkdir()
    dealer_dir.mkdir()
    family_dir.mkdir()
    monkeypatch.setattr(cfgmod, "_CONFIG_DIR", portal_dir)
    monkeypatch.setattr(cfgmod, "_DEALER_DIR", dealer_dir)
    monkeypatch.setattr(cfgmod, "_FAMILY_DIR", family_dir)
    return portal_dir, dealer_dir, family_dir


def _recording_seam():
    calls = []

    async def seam(domain, country, urls, is_e07):
        calls.append((domain, country, tuple(urls), is_e07))
        return len(urls)

    seam.calls = calls
    return seam


def _recording_purger():
    purged = []

    async def purge(urls):
        purged.append(tuple(urls))
        return len(urls)

    purge.purged = purged
    return purge


# ── 1. high-confidence family dealer → instantiated family recipe, not build_config ─
@pytest.mark.unit
def test_high_confidence_family_resolves_instantiated_recipe(isolated_stores):
    # Arrange — a WP-fingerprinting home (2 signals → high) on a dealer whose
    # per-dealer probe would ALSO succeed (sitemap_listing), plus an accepting family.
    _, dealer_dir, _ = isolated_stores
    cfgmod.save_family(_wordpress_family(min_confidence="high"))
    static = MapFetcher(_sitemap_pages("wp-garage.de", home=_WP_HOME_HIGH))

    # Act
    cfg, detection, newly = _run(
        resolve_or_detect_config("wp-garage.de", "DE", static_fetcher=static)
    )

    # Assert — the FAMILY recipe instantiated with this host won, NOT build_config
    # (build_config would have emitted strategy 'sitemap_listing' and host 'www.…').
    assert cfg is not None
    assert cfg.strategy == "wp_rest"
    assert cfg.source_key == "wp-garage.de"
    assert cfg.country == "DE"
    assert cfg.endpoints.host == "wp-garage.de"
    assert cfg.endpoints.sitemap_url == "https://wp-garage.de/wp-sitemap.xml"
    assert cfg.endpoints.api_url == "https://wp-garage.de/wp-json/wp/v2"
    # The signal that routed it, and the traceability note.
    assert detection is not None
    assert detection.cms == "wordpress" and detection.cms_confidence == "high"
    assert "family:wordpress" in detection.notes
    # Resolve-time view: nothing persisted, the family file stays the point of repair.
    assert newly is False
    assert not (dealer_dir / "wp-garage.de.json").exists()


# ── 2. no recognizable CMS → today's per-dealer route, byte-identical ────────────
@pytest.mark.unit
def test_no_cms_falls_back_to_per_dealer_build_config(isolated_stores):
    # Arrange — a family EXISTS in the store, but this dealer's home never fetches
    # (404 → home_html "") so no cms fires: presence of families must change nothing.
    _, dealer_dir, _ = isolated_stores
    cfgmod.save_family(_wordpress_family(min_confidence="medium"))
    static = MapFetcher(_sitemap_pages("dealer.example"))

    # Act
    cfg, detection, newly = _run(
        resolve_or_detect_config("dealer.example", "DE", static_fetcher=static)
    )

    # Assert — exactly today's path: detect → build_config → saved to the dealer store.
    assert cfg is not None and cfg.strategy == "sitemap_listing"
    assert newly is True
    assert (dealer_dir / "dealer.example.json").exists()
    assert detection.cms == "" and detection.cms_confidence == ""
    assert not any(n.startswith("family:") for n in detection.notes)


# ── 3. confidence floor: min_confidence='high' rejects a 'medium' verdict ────────
@pytest.mark.unit
def test_family_confidence_floor_rejects_medium_verdict(isolated_stores):
    # Arrange — ONE WP signal (→ medium) against a family demanding 'high'.
    _, dealer_dir, _ = isolated_stores
    cfgmod.save_family(_wordpress_family(min_confidence="high"))
    static = MapFetcher(_sitemap_pages("medium-wp.de", home=_WP_HOME_MEDIUM))

    # Act
    cfg, detection, newly = _run(
        resolve_or_detect_config("medium-wp.de", "DE", static_fetcher=static)
    )

    # Assert — the family did NOT accept: per-dealer build_config route, as today.
    assert cfg is not None and cfg.strategy == "sitemap_listing"
    assert newly is True
    assert (dealer_dir / "medium-wp.de.json").exists()
    # The signal was still attached (honest measurement), just not acted upon.
    assert detection.cms == "wordpress" and detection.cms_confidence == "medium"
    assert not any(n.startswith("family:") for n in detection.notes)


# ── 4. detect_web_type contract — no regression when no family is involved ───────
@pytest.mark.unit
def test_detect_web_type_contract_unchanged_without_family(isolated_stores):
    # Arrange — the canonical sitemap dealer from the pre-family detector tests.
    static = MapFetcher(_sitemap_pages("dealer.example"))

    # Act
    r = _run(detect_web_type("dealer.example", country="de", static_fetcher=static))

    # Assert — every pre-existing field exactly as before…
    assert r.ok and r.strategy == "sitemap_listing"
    assert r.discovery == "sitemap" and r.discovered == 2
    assert r.proof and r.proof["make"] == "BMW"
    assert r.classification == "sitemap_listing"
    assert r.spa_markers == ()
    # …and the new fields stay empty (additive defaults).
    assert r.cms == "" and r.cms_confidence == ""
    # Existing positional constructors (6 args) keep working untouched.
    legacy = DetectionResult("x.de", "DE", "none", False, "none", 0)
    assert legacy.cms == "" and legacy.cms_confidence == ""


# ── 5. opt-in: a cms verdict WITHOUT a family file changes nothing ────────────────
@pytest.mark.unit
def test_cms_signal_without_family_file_is_inert(isolated_stores):
    # Arrange — the home fingerprints WordPress (high), but the family store is EMPTY.
    _, dealer_dir, _ = isolated_stores
    static = MapFetcher(_sitemap_pages("wp-garage.de", home=_WP_HOME_HIGH))

    # Act
    cfg, detection, newly = _run(
        resolve_or_detect_config("wp-garage.de", "DE", static_fetcher=static)
    )

    # Assert — signal attached, behavior identical to today (per-dealer route).
    assert detection.cms == "wordpress" and detection.cms_confidence == "high"
    assert cfg is not None and cfg.strategy == "sitemap_listing"
    assert newly is True
    assert (dealer_dir / "wp-garage.de.json").exists()
    assert not any(n.startswith("family:") for n in detection.notes)


# ── 6. harvest end-to-end on a family-resolved dealer ─────────────────────────────
@pytest.mark.unit
def test_harvest_dealer_runs_on_family_resolved_config(isolated_stores):
    # Arrange
    _, dealer_dir, _ = isolated_stores
    cfgmod.save_family(_wordpress_family(min_confidence="high"))
    static = MapFetcher(_sitemap_pages("wp-garage.de", home=_WP_HOME_HIGH))
    seam = _recording_seam()
    purger = _recording_purger()

    # Act
    r = _run(harvest_dealer(
        "wp-garage.de", "de", static_fetcher=static, e07_fetcher=None,
        seam_runner=seam, purger=purger, limit=12,
    ))

    # Assert — the harvest ran on the FAMILY strategy (wp_rest is static → seam
    # is_e07=False), yielded, measured and purged exactly like any other dealer.
    assert r.web_type == "wp_rest"
    assert r.discovered == 2 and r.attempted == 2 and r.persisted == 2
    assert r.yields_inventory and r.purged and r.drift_ok
    assert r.newly_detected is False
    assert seam.calls and seam.calls[0][0] == "wp-garage.de" and seam.calls[0][3] is False
    # Bloque-D success contract (pre-existing): a 100%-proven scrape materializes a
    # versioned per-dealer recipe via emit() — create-if-absent, never clobbering.
    assert (dealer_dir / "wp-garage.de.json").exists()
