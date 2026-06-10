"""
Family-aware cage path — the CMS multiplier wired into ``harvest_t2_dealer``.

The cage path predated the multiplier and enumerated through the GENERIC cascade only,
so a family platform whose detail pages carry no vehicle path token (datamotive
``/p/<slug>-<id>``) caged ~0 URLs even after the probe had fingerprinted it. Covers:

  * a probe CMS verdict accepted by a family recipe routes through the recipe-pinned
    sitemap walk and cages the FULL detail set the generic cascade cannot see,
    with ``config_ref`` carrying the family-file provenance,
  * a verdict the family floor rejects keeps today's generic route byte-identical
    (per-dealer minimal config built and saved, dealers/ config_ref),
  * no verdict at all → generic route, untouched,
  * a saved per-dealer recipe wins over the family AND is never clobbered by the
    post-discovery minimal-config save.

All in-memory MapFetcher fakes + tmp-dir stores + recording cage — no network, no
Redis, no Postgres (mirrors ``test_family_wiring``).
"""
from __future__ import annotations

import asyncio
import json

import pytest

from scrapers.dealer_scraping import inventory_harvester as ih
from scrapers.pipeline.generic_extractor import FetchResult
from scrapers.portals import config as cfgmod
from scrapers.portals.config import (DriftBaseline, Endpoints, ExtractionConfig,
                                     FamilyEndpoints, FamilyMatch, FamilyRecipe)


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

    async def aclose(self) -> None:
        pass


def _b(text: str) -> bytes:
    return text.encode("utf-8")


def _run(coro):
    return asyncio.run(coro)


def _datamotive_family() -> FamilyRecipe:
    return FamilyRecipe(
        family_key="datamotive",
        strategy="sitemap_listing",
        matches=FamilyMatch(cms="datamotive", min_confidence="medium"),
        endpoints=FamilyEndpoints(
            sitemap_hint="/sitemap.xml",
            detail_url_re=r"^https?://[^/]+/(?:[^/]+/[^/]+/)?p/.+-\d+(?:-\d+)?$",
        ),
    )


def _datamotive_pages(domain: str, n: int = 5) -> dict[str, tuple[int, bytes]]:
    """A datamotive-shaped site: sitemapindex → vehicle shard → /p/<slug>-<id> details.

    The generic cascade keeps NONE of these (no vehicle path token in ``/p/…``), so any
    caged URL proves the recipe walk ran. Detail pages 404 — the enrich sample tolerates
    that and the cage records pointers regardless.
    """
    base = f"https://{domain}"
    shard = "<urlset>" + "".join(
        f"<url><loc>{base}/p/occasion-bmw-320d-{i}</loc></url>" for i in range(1, n + 1)
    ) + "</urlset>"
    index = ("<sitemapindex>"
             f"<sitemap><loc>{base}/sitemaps/vehicle-1.xml</loc></sitemap>"
             f"<sitemap><loc>{base}/sitemaps/pages-1.xml</loc></sitemap>"
             "</sitemapindex>")
    pages = "<urlset>" + f"<url><loc>{base}/over-ons</loc></url>" + "</urlset>"
    return {
        f"{base}/sitemap.xml": (200, _b(index)),
        f"{base}/sitemaps/vehicle-1.xml": (200, _b(shard)),
        f"{base}/sitemaps/pages-1.xml": (200, _b(pages)),
    }


@pytest.fixture()
def isolated_stores(tmp_path, monkeypatch):
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


@pytest.fixture()
def recording_cage(monkeypatch):
    """Replace the PG/Redis cage with a recorder — the unit under test is the
    URL-enumeration ROUTING, not the (already-covered) persistence."""
    calls: list[dict] = []

    async def cage(pg, rdb, domain, country, listings, *, config_ref=None):
        calls.append({"domain": domain, "country": country,
                      "urls": [li["url"] for li in listings], "config_ref": config_ref})
        return {"discovered": len(listings), "new": len(listings)}

    monkeypatch.setattr(ih, "cage_inventory", cage)
    return calls


def _patch_fetcher(monkeypatch, pages: dict[str, tuple[int, bytes]]) -> MapFetcher:
    fetcher = MapFetcher(pages)
    monkeypatch.setattr(ih, "make_dealer_fetcher", lambda: fetcher)
    return fetcher


# ── 1. accepted family verdict → recipe sitemap walk cages the full detail set ───
@pytest.mark.unit
def test_family_verdict_routes_recipe_walk_and_cages_full_set(
        isolated_stores, recording_cage, monkeypatch):
    # Arrange
    cfgmod.save_family(_datamotive_family())
    _patch_fetcher(monkeypatch, _datamotive_pages("pouw.example", n=5))

    # Act
    r = _run(ih.harvest_t2_dealer(None, None, "pouw.example", "NL",
                                  cms="datamotive", cms_confidence="medium"))

    # Assert — all 5 /p/ details (invisible to the generic cascade) reached the cage,
    # and the entity row will carry the FAMILY file as provenance.
    assert r["method"] == "recipe:sitemap_listing"
    assert r["discovered"] == 5 and r["new"] == 5 and r["yields"]
    assert recording_cage and len(recording_cage[0]["urls"]) == 5
    assert all("/p/occasion-bmw-320d-" in u for u in recording_cage[0]["urls"])
    assert recording_cage[0]["config_ref"] == "configs/families/datamotive.json"


# ── 2. family floor rejects the verdict → today's generic route, config saved ────
@pytest.mark.unit
def test_rejected_verdict_keeps_generic_route(isolated_stores, recording_cage, monkeypatch):
    # Arrange — floor 'high', verdict 'medium'; site exposes a GENERIC sitemap with
    # vehicle-token paths so the cascade yields on its own.
    _, dealer_dir, _ = isolated_stores
    fam = FamilyRecipe(
        family_key="datamotive", strategy="sitemap_listing",
        matches=FamilyMatch(cms="datamotive", min_confidence="high"),
        endpoints=FamilyEndpoints(sitemap_hint="/sitemap.xml", detail_url_re=r"/p/.+-\d+$"),
    )
    cfgmod.save_family(fam)
    base = "https://generic.example"
    sm = ("<urlset>"
          f"<url><loc>{base}/vehicles/bmw-320d-1</loc></url>"
          f"<url><loc>{base}/vehicles/audi-a4-2</loc></url>"
          "</urlset>")
    _patch_fetcher(monkeypatch, {
        f"{base}/robots.txt": (200, _b(f"Sitemap: {base}/sitemap.xml")),
        f"{base}/sitemap.xml": (200, _b(sm)),
    })

    # Act
    r = _run(ih.harvest_t2_dealer(None, None, "generic.example", "NL",
                                  cms="datamotive", cms_confidence="medium"))

    # Assert — generic cascade ran (method is the cascade's, not recipe:*), the minimal
    # per-dealer config materialized, and config_ref points at the dealers store.
    assert r["method"] == "sitemap"
    assert r["discovered"] == 2
    assert recording_cage[0]["config_ref"] == "configs/dealers/generic.example.json"
    assert (dealer_dir / "generic.example.json").exists()


# ── 3. no verdict → generic route untouched ───────────────────────────────────────
@pytest.mark.unit
def test_no_cms_keeps_generic_route(isolated_stores, recording_cage, monkeypatch):
    # Arrange — a family EXISTS but this dealer carries no verdict: must change nothing.
    _, dealer_dir, _ = isolated_stores
    cfgmod.save_family(_datamotive_family())
    base = "https://plain.example"
    sm = f"<urlset><url><loc>{base}/vehicles/seat-arona-9</loc></url></urlset>"
    _patch_fetcher(monkeypatch, {
        f"{base}/robots.txt": (200, _b(f"Sitemap: {base}/sitemap.xml")),
        f"{base}/sitemap.xml": (200, _b(sm)),
    })

    # Act
    r = _run(ih.harvest_t2_dealer(None, None, "plain.example", "NL"))

    # Assert
    assert r["method"] == "sitemap" and r["discovered"] == 1
    assert recording_cage[0]["config_ref"] == "configs/dealers/plain.example.json"
    assert (dealer_dir / "plain.example.json").exists()


# ── 4b. a MINIMAL auto-generated recipe never shadows an accepting family ─────────
@pytest.mark.unit
def test_minimal_auto_recipe_is_outranked_by_family(
        isolated_stores, recording_cage, monkeypatch):
    # Arrange — the blind-cascade stub a previous cage run materialized (no
    # detail_url_re / field_map / api_url, floor 4 — pouw.nl's real 2026-06-10 state)
    # PLUS an accepting datamotive family. The family walk must win.
    _, dealer_dir, _ = isolated_stores
    cfgmod.save_family(_datamotive_family())
    stub = ExtractionConfig(
        source_key="pouw.example", country="NL", strategy="jsonld_detail", version=1,
        endpoints=Endpoints(host="www.pouw.example"),
        drift_baseline=DriftBaseline(expected_min_volume=4))
    cfgmod.save(stub, kind="dealer")
    _patch_fetcher(monkeypatch, _datamotive_pages("pouw.example", n=5))

    # Act
    r = _run(ih.harvest_t2_dealer(None, None, "pouw.example", "NL",
                                  cms="datamotive", cms_confidence="high"))

    # Assert — family route, full set, family provenance; the stub stays on disk
    # untouched (the family view is never persisted over it).
    assert r["method"] == "recipe:sitemap_listing"
    assert r["discovered"] == 5
    assert recording_cage[0]["config_ref"] == "configs/families/datamotive.json"
    assert json.loads((dealer_dir / "pouw.example.json").read_text(encoding="utf-8"))[
        "strategy"] == "jsonld_detail"


# ── 4. saved per-dealer recipe wins and is never clobbered ────────────────────────
@pytest.mark.unit
def test_saved_dealer_recipe_wins_and_is_not_clobbered(
        isolated_stores, recording_cage, monkeypatch):
    # Arrange — a hand-tuned per-dealer recipe pinning sitemap+detail_url_re (version 7
    # marks it as curated); the family store also has an accepting recipe.
    _, dealer_dir, _ = isolated_stores
    cfgmod.save_family(_datamotive_family())
    saved = ExtractionConfig(
        source_key="tuned.example", country="NL", strategy="sitemap_listing", version=7,
        endpoints=Endpoints(host="tuned.example",
                            sitemap_url="https://tuned.example/sitemap.xml",
                            detail_url_re=r"/p/.+-\d+$"),
        drift_baseline=DriftBaseline(expected_min_volume=3))
    cfgmod.save(saved, kind="dealer")
    before = (dealer_dir / "tuned.example.json").read_text(encoding="utf-8")
    _patch_fetcher(monkeypatch, _datamotive_pages("tuned.example", n=3))

    # Act
    r = _run(ih.harvest_t2_dealer(None, None, "tuned.example", "NL",
                                  cms="datamotive", cms_confidence="medium"))

    # Assert — recipe route, dealers provenance, and the saved file byte-identical
    # (the old post-discovery minimal-config save would have clobbered version 7 → 1).
    assert r["method"] == "recipe:sitemap_listing"
    assert r["discovered"] == 3
    assert recording_cage[0]["config_ref"] == "configs/dealers/tuned.example.json"
    after = (dealer_dir / "tuned.example.json").read_text(encoding="utf-8")
    assert after == before
    assert json.loads(after)["version"] == 7
