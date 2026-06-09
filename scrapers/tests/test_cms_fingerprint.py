"""
CMS fingerprint — pure HTML/headers → family verdict, fully in memory.

One minimal-but-realistic HTML fragment per platform family, plus the verdict
mechanics: unknown fallback, high-vs-medium confidence, and specific platforms
beating the generic wordpress when both coexist. No network, no DB, no browser —
the repo convention for detector tests.
"""
from __future__ import annotations

import pytest

from scrapers.dealer_scraping.cms_fingerprint import CmsVerdict, fingerprint_cms


# ── one family per test, minimal realistic markup ───────────────────────────────
@pytest.mark.unit
def test_detects_izmocars_from_cdn_asset():
    # Arrange
    html = '<html><body><script src="https://cdn.izmocars.com/widget.js"></script></body></html>'

    # Act
    verdict = fingerprint_cms(html)

    # Assert
    assert verdict.cms == "izmocars"
    assert verdict.signals == ("cdn.izmocars",)


@pytest.mark.unit
def test_detects_dealer_com_from_static_host_via_embedded_dms():
    # Arrange — src host hits detect_embedded_dms's 'dealer.com' provider entry
    html = '<script src="https://static.dealer.com/v9/global.js"></script>'

    # Act
    verdict = fingerprint_cms(html)

    # Assert
    assert verdict.cms == "dealer_com"
    assert "dealer.com-host" in verdict.signals


@pytest.mark.unit
def test_detects_dealer_com_from_ddc_class_prefix():
    # Arrange
    html = '<div class="ddc-content ddc-wrapper">inventory</div>'

    # Act
    verdict = fingerprint_cms(html)

    # Assert
    assert verdict.cms == "dealer_com"
    assert verdict.signals == ("ddc-class",)


@pytest.mark.unit
def test_detects_dealerk_from_iframe_host():
    # Arrange
    html = '<iframe src="https://widget.dealerk.it/stock"></iframe>'

    # Act
    verdict = fingerprint_cms(html)

    # Assert
    assert verdict.cms == "dealerk"
    assert "dealerk-host" in verdict.signals


@pytest.mark.unit
def test_detects_modix_from_gw_trends_host():
    # Arrange — 'gw-trends' is covered by detect_embedded_dms's provider table
    html = '<iframe data-src="https://gw-trends.de/showroom/123"></iframe>'

    # Act
    verdict = fingerprint_cms(html)

    # Assert
    assert verdict.cms == "modix"
    assert "gw-trends-host" in verdict.signals


@pytest.mark.unit
def test_detects_planetvo_from_autralis_host():
    # Arrange
    html = '<script src="https://stock.autralis.com/embed.js"></script>'

    # Act
    verdict = fingerprint_cms(html)

    # Assert
    assert verdict.cms == "planetvo"
    assert "autralis-host" in verdict.signals


@pytest.mark.unit
def test_detects_incadea_from_dms_host():
    # Arrange
    html = '<iframe src="https://dms.incadea.net/inventory"></iframe>'

    # Act
    verdict = fingerprint_cms(html)

    # Assert
    assert verdict.cms == "incadea"
    assert verdict.signals == ("incadea-host",)


@pytest.mark.unit
def test_detects_next_dealer_when_next_marker_and_vehicle_jsonld_coexist():
    # Arrange — Next.js shell on home, JSON-LD Car on the sampled detail page
    home = '<html><body><div id="__next"></div><script id="__NEXT_DATA__" type="application/json">{}</script></body></html>'
    detail = '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Car","model":"320d"}</script>'

    # Act
    verdict = fingerprint_cms(home, sample_detail_html=detail)

    # Assert
    assert verdict.cms == "next_dealer"
    assert "spa:next" in verdict.signals and "vehicle:jsonld-car" in verdict.signals


@pytest.mark.unit
def test_next_marker_without_vehicle_signal_is_not_next_dealer():
    # Arrange — a Next.js site with zero vehicle evidence (could be any business)
    home = '<script id="__NEXT_DATA__" type="application/json">{}</script>'

    # Act
    verdict = fingerprint_cms(home)

    # Assert
    assert verdict.cms == "unknown"


@pytest.mark.unit
def test_detects_nuxt_dealer_from_nuxt_marker():
    # Arrange
    home = "<html><body><script>window.__NUXT__={state:{}}</script></body></html>"

    # Act
    verdict = fingerprint_cms(home)

    # Assert
    assert verdict.cms == "nuxt_dealer"
    assert verdict.signals == ("spa:nuxt",)


@pytest.mark.unit
def test_detects_wordpress_from_wp_content_path():
    # Arrange
    html = '<link rel="stylesheet" href="/wp-content/themes/dealer/style.css">'

    # Act
    verdict = fingerprint_cms(html)

    # Assert
    assert verdict.cms == "wordpress"
    assert verdict.signals == ("wp-content",)


@pytest.mark.unit
def test_detects_wordpress_from_meta_generator():
    # Arrange
    html = '<head><meta name="generator" content="WordPress 6.4.2"></head>'

    # Act
    verdict = fingerprint_cms(html)

    # Assert
    assert verdict.cms == "wordpress"
    assert verdict.signals == ("meta-generator-wordpress",)


@pytest.mark.unit
def test_detects_symfony_from_debug_header_and_sf_cookie():
    # Arrange — plain HTML, the evidence lives only in the response headers
    headers = {
        "X-Debug-Token": "a1b2c3",
        "Set-Cookie": "sf-session=xyz; Path=/",
    }

    # Act
    verdict = fingerprint_cms("<html><body>garage</body></html>", headers=headers)

    # Assert
    assert verdict.cms == "symfony"
    assert verdict.signals == ("header:x-debug-token", "cookie:sf-")
    assert verdict.confidence == "high"


# ── verdict mechanics ────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_unknown_when_no_marker_fires():
    # Arrange
    html = "<html><body><h1>Garage Dupont</h1><p>Voitures de qualite.</p></body></html>"

    # Act
    verdict = fingerprint_cms(html, headers={"Content-Type": "text/html"})

    # Assert
    assert verdict == CmsVerdict(cms="unknown", confidence="unknown", signals=())


@pytest.mark.unit
def test_confidence_high_with_two_signals_vs_medium_with_one():
    # Arrange
    two_markers = '<link href="/wp-content/x.css"><script src="/wp-json/wp/v2/types"></script>'
    one_marker = '<link href="/wp-content/x.css">'

    # Act
    high = fingerprint_cms(two_markers)
    medium = fingerprint_cms(one_marker)

    # Assert
    assert high.cms == "wordpress" and high.confidence == "high"
    assert high.signals == ("wp-content", "wp-json")
    assert medium.cms == "wordpress" and medium.confidence == "medium"
    assert medium.signals == ("wp-content",)


@pytest.mark.unit
def test_specific_platform_beats_generic_wordpress_when_both_coexist():
    # Arrange — a WordPress shell whose inventory is an embedded izmocars widget
    html = (
        '<link rel="stylesheet" href="/wp-content/themes/x/style.css">'
        '<meta name="generator" content="WordPress 6.2">'
        '<script src="https://cdn.izmocars.com/showroom.js" data-izmo="stock"></script>'
    )

    # Act
    verdict = fingerprint_cms(html)

    # Assert — the family routes to the widget recipe, not the shell's
    assert verdict.cms == "izmocars"
    assert verdict.confidence == "high"  # data-izmo + cdn.izmocars = 2 distinct signals
    assert "wp-content" not in verdict.signals


@pytest.mark.unit
def test_dms_platform_beats_generic_wordpress_when_both_coexist():
    # Arrange — WordPress shell embedding its stock from a Modix iframe
    html = (
        '<link href="/wp-json/">'
        '<iframe src="https://modix.example.de/widget"></iframe>'
    )

    # Act
    verdict = fingerprint_cms(html)

    # Assert
    assert verdict.cms == "modix"
    assert verdict.confidence == "medium"


@pytest.mark.unit
def test_verdict_is_frozen_and_hashable():
    # Arrange / Act
    verdict = fingerprint_cms('<div class="ddc-x"></div>')

    # Assert — frozen dataclass: usable as a routing key, immune to mutation
    with pytest.raises(Exception):
        verdict.cms = "other"  # type: ignore[misc]
    assert hash(verdict) == hash(CmsVerdict("dealer_com", "medium", ("ddc-class",)))
