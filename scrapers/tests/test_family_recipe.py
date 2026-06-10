"""
Family recipe store — ONE parametric recipe per platform/CMS (``configs/families/``)
instantiated per dealer host: the "1 recipe = N sites of the same CMS" multiplier.

These cover the additive extension to ``scrapers/portals/config.py``:
  * family save/load round-trips through the family dir (per-CMS key),
  * ``instantiate_family`` fills a dealer host into the platform patterns,
  * ``load()`` resolution order: curated portal > dealer > family-by-CMS,
  * ``cms=None`` keeps ``load()`` byte-identical to the pre-family resolver,
  * a missing family resolves to a clean None (no exception),
  * the git-tracked recipes in ``configs/families/`` parse and stay honest.

All in-memory / tmp-dir — no network, no DB.
"""
from __future__ import annotations

import pytest

from scrapers.portals import config as cfgmod
from scrapers.portals.config import (
    DriftBaseline,
    Endpoints,
    ExtractionConfig,
    FamilyEndpoints,
    FamilyMatch,
    FamilyRecipe,
    Provenance,
    family_from_dict,
    family_to_dict,
    instantiate_family,
)


def _family(cms: str = "dealer_com") -> FamilyRecipe:
    return FamilyRecipe(
        family_key=cms,
        strategy="jsonld_detail",
        matches=FamilyMatch(cms=cms, min_confidence="high"),
        endpoints=FamilyEndpoints(
            sitemap_hint="/sitemap-inventory.xml",
            catalog_path_tokens=("used-inventory", "inventory"),
            detail_url_re=r"/used-[\w-]+/vehicle/\d+",
        ),
        drift_baseline=DriftBaseline(
            expected_min_volume=1, required_fields=("make", "model", "year", "price")
        ),
    )


def _source_cfg(domain: str, strategy: str, country: str = "FR") -> ExtractionConfig:
    return ExtractionConfig(
        source_key=domain,
        country=country,
        strategy=strategy,
        endpoints=Endpoints(host=f"www.{domain}", sitemap_url=f"https://{domain}/sitemap.xml"),
    )


@pytest.fixture()
def isolated_stores(tmp_path, monkeypatch):
    """Point all three config stores at empty tmp dirs so tests never touch the repo."""
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


# ── store: save/load round-trip by CMS key ─────────────────────────────────────
@pytest.mark.unit
def test_family_save_load_round_trip_by_cms(isolated_stores):
    # Arrange
    _, _, family_dir = isolated_stores
    recipe = _family("dealer_com")

    # Act
    path = cfgmod.save_family(recipe)
    loaded = cfgmod.load_family("dealer_com")

    # Assert — per-CMS file in the family dir, tuples survive the JSON round-trip.
    assert path == family_dir / "dealer_com.json"
    assert loaded == recipe
    assert loaded.endpoints.catalog_path_tokens == ("used-inventory", "inventory")
    assert loaded.provenance.verified_count == 0


@pytest.mark.unit
def test_family_dict_round_trip_preserves_provenance(isolated_stores):
    # Arrange
    recipe = FamilyRecipe(
        family_key="izmocars",
        strategy="sitemap_listing",
        provenance=Provenance(
            verified_on_dealers=("a.fr", "b.de"), verified_count=2,
            verified_date="2026-06-10", tool="close_entity",
        ),
    )

    # Act
    back = family_from_dict(family_to_dict(recipe))

    # Assert
    assert back == recipe
    assert back.provenance.verified_on_dealers == ("a.fr", "b.de")


# ── instantiation: the dealer host fills the platform patterns ────────────────
@pytest.mark.unit
def test_instantiate_fills_dealer_host_into_endpoints(isolated_stores):
    # Arrange
    recipe = _family("dealer_com")

    # Act
    cfg = instantiate_family(recipe, "garage-dupont.fr")

    # Assert — every endpoint is concrete for THIS host, strategy/baseline inherited.
    assert isinstance(cfg, ExtractionConfig)
    assert cfg.source_key == "garage-dupont.fr"
    assert cfg.country == "FR"  # derived from the TLD
    assert cfg.strategy == "jsonld_detail"
    assert cfg.endpoints.host == "garage-dupont.fr"
    assert cfg.endpoints.sitemap_url == "https://garage-dupont.fr/sitemap-inventory.xml"
    assert cfg.endpoints.listing_url_template == "https://garage-dupont.fr/used-inventory"
    assert cfg.endpoints.detail_url_re == r"/used-[\w-]+/vehicle/\d+"
    assert cfg.drift_baseline.required_fields == ("make", "model", "year", "price")


@pytest.mark.unit
def test_instantiate_normalizes_scheme_www_and_explicit_country(isolated_stores):
    # Arrange
    recipe = _family("dealer_com")

    # Act
    cfg = instantiate_family(recipe, "https://www.autohaus-beispiel.de/", country="DE")

    # Assert — host keeps www, source_key is the canonical bare domain.
    assert cfg.endpoints.host == "www.autohaus-beispiel.de"
    assert cfg.source_key == "autohaus-beispiel.de"
    assert cfg.country == "DE"
    assert cfg.endpoints.sitemap_url == "https://www.autohaus-beispiel.de/sitemap-inventory.xml"


@pytest.mark.unit
def test_instantiate_unknown_tld_falls_back_to_zz(isolated_stores):
    # Arrange / Act
    cfg = instantiate_family(_family(), "dealer.example")

    # Assert — honest unknown (ISO 3166-1 user-assigned), never an invented country.
    assert cfg.country == "ZZ"


@pytest.mark.unit
def test_instantiate_api_hint_feeds_api_url(isolated_stores):
    # Arrange — a wp_rest-style family whose API root is a host-relative hint.
    recipe = FamilyRecipe(
        family_key="wordpress",
        strategy="wp_rest",
        endpoints=FamilyEndpoints(sitemap_hint="/wp-sitemap.xml", api_path_hint="/wp-json/wp/v2"),
    )

    # Act
    cfg = instantiate_family(recipe, "autobedrijf-x.nl")

    # Assert
    assert cfg.endpoints.api_url == "https://autobedrijf-x.nl/wp-json/wp/v2"
    assert cfg.endpoints.sitemap_url == "https://autobedrijf-x.nl/wp-sitemap.xml"
    assert cfg.endpoints.listing_url_template == ""  # no catalog tokens declared
    assert cfg.country == "NL"


# ── load(): resolution order portal > dealer > family ─────────────────────────
@pytest.mark.unit
def test_load_with_cms_resolves_family_for_unknown_dealer(isolated_stores):
    # Arrange — no per-source recipe anywhere, only the family.
    cfgmod.save_family(_family("dealer_com"))

    # Act
    cfg = cfgmod.load("garage-neuf.fr", cms="dealer_com")

    # Assert — a concrete, host-filled config came out of the parametric recipe.
    assert cfg is not None
    assert cfg.source_key == "garage-neuf.fr"
    assert cfg.endpoints.host == "garage-neuf.fr"
    assert cfg.endpoints.sitemap_url == "https://garage-neuf.fr/sitemap-inventory.xml"


@pytest.mark.unit
def test_resolution_order_portal_beats_dealer_beats_family(isolated_stores):
    # Arrange — the SAME domain has a recipe in all three stores, each distinguishable.
    portal_dir, dealer_dir, _ = isolated_stores
    domain = "overlap.fr"
    cfgmod.save(_source_cfg(domain, "sitemap_listing"), kind="portal")
    cfgmod.save(_source_cfg(domain, "playwright_meta"), kind="dealer")
    cfgmod.save_family(_family("dealer_com"))  # family strategy = jsonld_detail

    # Act / Assert — curated portal wins over both.
    assert cfgmod.load(domain, cms="dealer_com").strategy == "sitemap_listing"

    # Act / Assert — remove the portal recipe: the dealer-specific one wins next.
    (portal_dir / f"{domain}.json").unlink()
    assert cfgmod.load(domain, cms="dealer_com").strategy == "playwright_meta"

    # Act / Assert — remove the dealer recipe too: the family is the last resort.
    (dealer_dir / f"{domain}.json").unlink()
    assert cfgmod.load(domain, cms="dealer_com").strategy == "jsonld_detail"


@pytest.mark.unit
def test_load_without_cms_is_backward_compatible(isolated_stores):
    # Arrange — a family exists, but the caller does not pass a cms (today's callers).
    cfgmod.save_family(_family("dealer_com"))

    # Act / Assert — identical to the pre-family resolver: no per-source file → None.
    assert cfgmod.load("garage-neuf.fr") is None

    # Arrange — and when a per-source recipe exists, it resolves exactly as before.
    cfgmod.save(_source_cfg("garage-neuf.fr", "sitemap_listing"), kind="dealer")

    # Act / Assert
    assert cfgmod.load("garage-neuf.fr").strategy == "sitemap_listing"


@pytest.mark.unit
def test_unknown_family_returns_clean_none(isolated_stores):
    # Act / Assert — no file for that cms: clean None at both layers, no exception.
    assert cfgmod.load_family("no-such-cms") is None
    assert cfgmod.load("garage-neuf.fr", cms="no-such-cms") is None


@pytest.mark.unit
def test_list_configs_family_kind_is_a_separate_namespace(isolated_stores):
    # Arrange
    cfgmod.save_family(_family("dealer_com"))
    cfgmod.save_family(FamilyRecipe(family_key="wordpress", strategy="wp_rest"))
    cfgmod.save(_source_cfg("p1.nl", "sitemap_listing", country="NL"), kind="portal")

    # Act / Assert — family keys list under their own kind and never leak into "all"
    # (CMS names are not source_keys).
    assert cfgmod.list_configs("family") == ["dealer_com", "wordpress"]
    assert cfgmod.list_configs("all") == ["p1.nl"]


# ── matches gate + repo-tracked recipes stay coherent ─────────────────────────
@pytest.mark.unit
def test_family_accepts_enforces_cms_and_confidence_floor():
    # Arrange
    recipe = _family("dealer_com")  # min_confidence = high

    # Act / Assert
    assert recipe.accepts("dealer_com", "high") is True
    assert recipe.accepts("dealer_com", "medium") is False
    assert recipe.accepts("wordpress", "high") is False


@pytest.mark.unit
def test_repo_family_recipes_parse_and_are_honest():
    # Arrange — the git-tracked store shipped with the repo (read-only check).
    keys = cfgmod.list_configs("family")

    # Act / Assert — every shipped recipe parses, matches its filename, declares a
    # known strategy, and carries an HONEST provenance (nothing claimed verified).
    assert "dealer_com" in keys and "wordpress" in keys
    for key in keys:
        recipe = cfgmod.load_family(key)
        assert recipe is not None
        assert recipe.family_key == key
        assert recipe.kind == "family"
        assert recipe.strategy in cfgmod.STRATEGIES
        assert recipe.provenance.verified_count == len(recipe.provenance.verified_on_dealers)
