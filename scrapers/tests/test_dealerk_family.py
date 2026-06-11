"""dealerk family recipe + locale-variant listing-root candidates (the multiplier).

dealerk (MotorK/WebSparK) exposes its live stock at a LOCALE-VARIANT listing root
(/coches/ ES, /voitures/ FR). The family recipe declares them as candidate tokens;
instantiate_family turns them into per-host candidate roots that discover tries in
order — so ONE recipe is availability-first-correct across all six countries.
"""
import re

from scrapers.portals import config


def test_instantiate_family_builds_locale_candidate_roots():
    # Arrange: a family recipe with several locale listing tokens.
    recipe = config.FamilyRecipe(
        family_key="dealerk",
        strategy="jsonld_detail",
        matches=config.FamilyMatch(cms="dealerk", min_confidence="medium"),
        endpoints=config.FamilyEndpoints(
            sitemap_hint="/sitemap_index.xml",
            catalog_path_tokens=("coches", "voitures", "occasions"),
            detail_url_re=r"^https?://[^/]+(?:/[a-z0-9-]+){7}/\d{5,8}/$",
        ),
    )
    # Act
    cfg = config.instantiate_family(recipe, "www.priorauto.com", country="ES")
    # Assert: primary = first token; candidates = every locale root, host-filled.
    assert cfg.endpoints.listing_url_template == "https://www.priorauto.com/coches"
    assert cfg.endpoints.listing_url_candidates == (
        "https://www.priorauto.com/coches",
        "https://www.priorauto.com/voitures",
        "https://www.priorauto.com/occasions",
    )
    assert cfg.source_key == "priorauto.com"
    assert cfg.strategy == "jsonld_detail"


def test_dealerk_recipe_loads_and_accepts_its_family():
    recipe = config.load_family("dealerk")
    assert recipe is not None
    assert recipe.strategy == "jsonld_detail"
    assert recipe.accepts("dealerk", "medium")
    assert not recipe.accepts("wordpress", "high")
    assert "coches" in recipe.endpoints.catalog_path_tokens
    assert recipe.endpoints.detail_url_re


def test_dealerk_detail_re_isolates_pdps_from_categories():
    recipe = config.load_family("dealerk")
    rx = re.compile(recipe.endpoints.detail_url_re)
    # a real PDP (7 path segments + numeric stock id) matches
    assert rx.search(
        "https://www.priorauto.com/coches/segunda-mano/la-coruna/alfa-romeo/"
        "stelvio/diesel/2-2-diesel-190cv-awd-sprint-q4/1158542/"
    )
    # the listing root / a category is NOT a PDP
    assert not rx.search("https://www.priorauto.com/coches/")
