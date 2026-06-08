"""
Bloque E — adversarial count verification ("CARDEX no vende mentiras") gate.

Pure-function re-derivation of an entity's inventory count by methods INDEPENDENT of the
harvest pipeline, plus the convergence gate that caught the dacia 17-vs-229 sub-count.
"""
from __future__ import annotations

import pytest

from scrapers.intelligence import count_verify as cv

# dacia-shaped sitemap: 2 real /stock/ PDPs, 1 category index, 1 CMS page.
SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://www.d.fr/stock/occasion-2018-renault-clio-100493-4850989-fr-fr.htm</loc></url>
<url><loc>https://www.d.fr/stock/demonstration-2025-dacia-bigster-4780479-fr-fr.htm</loc></url>
<url><loc>https://www.d.fr/occasion-peugeot-208-fr-fr.htm</loc></url>
<url><loc>https://www.d.fr/contact-fr-fr.htm</loc></url>
</urlset>"""


@pytest.mark.unit
def test_count_pdp_in_sitemap_matches_recipe_pattern():
    # 2 PDPs under /stock/; category index + CMS page excluded.
    assert cv.count_pdp_in_sitemap(SITEMAP, "/stock/") == 2


@pytest.mark.unit
def test_count_pdp_dedup_and_empty_pattern():
    dupe = SITEMAP.replace(
        "</urlset>",
        "<url><loc>https://www.d.fr/stock/occasion-2018-renault-clio-100493-4850989-fr-fr.htm</loc></url></urlset>",
    )
    assert cv.count_pdp_in_sitemap(dupe, "/stock/") == 2  # distinct (dedup)
    assert cv.count_pdp_in_sitemap(SITEMAP, "") == 0       # no pattern → no claim


@pytest.mark.unit
def test_count_jsonld_total_numberofitems():
    html = '<script type="application/ld+json">{"@type":"ItemList","numberOfItems":229}</script>'
    assert cv.count_jsonld_total(html) == 229


@pytest.mark.unit
def test_count_jsonld_total_itemlist_len_and_absent():
    html = '<script type="application/ld+json">{"itemListElement":[{"a":1},{"a":2},{"a":3}]}</script>'
    assert cv.count_jsonld_total(html) == 3
    assert cv.count_jsonld_total("<html>no jsonld here</html>") is None


@pytest.mark.unit
def test_cross_check_converges_dacia():
    v = cv.cross_check(229, {"sitemap": 229, "jsonld": 229})
    assert v.trustworthy and v.converged
    assert v.max_divergence == 0.0


@pytest.mark.unit
def test_cross_check_catches_the_lie():
    # The exact dacia failure: pipeline claims 17 but the sitemap proves 229.
    v = cv.cross_check(17, {"sitemap": 229})
    assert not v.trustworthy
    assert v.max_divergence > 0.9


@pytest.mark.unit
def test_cross_check_untrustworthy_without_independent_method():
    assert not cv.cross_check(100, {"sitemap": 0}).trustworthy
    assert not cv.cross_check(0, {"sitemap": 0}).trustworthy


@pytest.mark.unit
def test_cross_check_tolerance_allows_small_live_drift():
    # A couple of cars sold between snapshots → within tolerance, still trustworthy.
    v = cv.cross_check(229, {"sitemap": 227}, tolerance=0.02)
    assert v.trustworthy
