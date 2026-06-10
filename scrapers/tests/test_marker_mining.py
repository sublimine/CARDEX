"""Marker mining — pure extraction + aggregation (no I/O)."""
from __future__ import annotations

import pytest

from scrapers.dealer_scraping.marker_mining import aggregate_markers, extract_markers


@pytest.mark.unit
def test_extracts_generator_version_normalized():
    # Arrange
    html = '<html><head><meta name="generator" content="WordPress 6.5.2"></head></html>'

    # Act
    markers = extract_markers(html, site_host="garage.nl")

    # Assert
    assert ("generator", "wordpress") in markers


@pytest.mark.unit
def test_extracts_external_saas_host_but_drops_noise_and_self():
    # Arrange — one platform CDN, one analytics noise host, one self-hosted asset.
    html = (
        '<script src="https://cdn.dealerplatform.nl/widget.js"></script>'
        '<script src="https://www.googletagmanager.com/gtag.js"></script>'
        '<link href="https://www.garage.nl/theme/main.css">'
    )

    # Act
    markers = extract_markers(html, site_host="garage.nl")

    # Assert — only the SaaS origin survives (registrable-domain form).
    assert ("ext_host", "dealerplatform.nl") in markers
    assert not any(v == "googletagmanager.com" for k, v in markers if k == "ext_host")
    assert not any(v == "garage.nl" for k, v in markers if k == "ext_host")


@pytest.mark.unit
def test_extracts_internal_path_token_and_js_marker():
    # Arrange — typo3 layout: /typo3conf/ asset + fileadmin marker in raw HTML.
    html = (
        '<link rel="stylesheet" href="/typo3conf/ext/site/style.css">'
        '<img src="/fileadmin/cars/golf.jpg">'
    )

    # Act
    markers = extract_markers(html, site_host="autohaus.de")

    # Assert — the path token AND the known js_marker both fire.
    assert ("path_token", "typo3conf") in markers
    assert ("js_marker", "typo3") in markers


@pytest.mark.unit
def test_generic_path_tokens_are_noise():
    # Arrange
    html = '<script src="/js/app.js"></script><link href="/css/site.css">'

    # Act
    markers = extract_markers(html, site_host="x.nl")

    # Assert
    assert not any(k == "path_token" for k, _ in markers)


@pytest.mark.unit
def test_empty_html_yields_empty_set():
    assert extract_markers("", site_host="x.nl") == frozenset()


@pytest.mark.unit
def test_aggregate_ranks_by_domain_reach_and_drops_singletons():
    # Arrange — marker A on 3 domains, marker B on 2, marker C on 1 (noise).
    a = ("ext_host", "dealerplatform.nl")
    b = ("js_marker", "typo3")
    c = ("path_token", "weird-once")
    per_domain = {
        "d1.nl": frozenset({a, b}),
        "d2.nl": frozenset({a, b, c}),
        "d3.nl": frozenset({a}),
    }

    # Act
    ranked = aggregate_markers(per_domain, min_domains=2)

    # Assert — ordered by reach, singleton dropped, samples carried.
    assert [r["domains"] for r in ranked] == [3, 2]
    assert ranked[0]["kind"] == "ext_host" and ranked[0]["value"] == "dealerplatform.nl"
    assert ranked[0]["sample"] == ["d1.nl", "d2.nl", "d3.nl"]
    assert all(r["value"] != "weird-once" for r in ranked)
