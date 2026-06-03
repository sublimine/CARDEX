"""
Intelligence tests — poison (D3), WAF classifier (D1), schema-drift (D2).

Poison and WAF are pure functions exercised over crafted HTML/header inputs;
schema-drift runs against the in-memory `conn` to verify the registry transitions
(first observation → unchanged sample → real change).
"""
from __future__ import annotations

import pytest

from scrapers.intelligence import poison, schema, waf

# ── poison (D3) ───────────────────────────────────────────────────────────────
# A realistic, markup-heavy listing well over the 15KB floor with a Car JSON-LD.
_GOOD_HTML = (
    '<html><head><script type="application/ld+json">{"@type":"Car"}</script></head><body>'
    + '<div class="listing"><span data-x="1">content</span></div>' * 400
    + "</body></html>"
)


@pytest.mark.unit
def test_poison_clean_page_passes():
    verdict = poison.detect(_GOOD_HTML, image_urls=("https://cdn.portal.de/a.jpg",))
    assert not verdict.is_poison
    assert verdict.score == 0
    assert verdict.reason == "clean"


@pytest.mark.unit
def test_poison_article_plus_tiny_html_two_signals():
    html = '<script type="application/ld+json">{"@type":"BlogPosting"}</script>' + "prose " * 40
    verdict = poison.detect(html)
    assert poison.SIG_ARTICLE_TYPE in verdict.signals
    assert poison.SIG_TINY_HTML in verdict.signals
    assert verdict.is_poison  # 2 signals >= threshold


@pytest.mark.unit
def test_poison_single_signal_below_threshold():
    # Tiny HTML alone (one signal) must not condemn the page.
    html = "<html><body><div>" + "<span>x</span>" * 5 + "</div></body></html>"
    verdict = poison.detect(html)
    assert verdict.score == 1
    assert not verdict.is_poison


@pytest.mark.unit
def test_poison_text_code_ratio_flag():
    # Almost pure prose, no markup → ratio > 0.8.
    html = "word " * 4000
    assert poison.SIG_TEXT_CODE_RATIO in poison.detect(html).signals


@pytest.mark.unit
def test_poison_cloudflare_images_flag():
    verdict = poison.detect(_GOOD_HTML, image_urls=("https://portal.imagedelivery.net/abc/1.jpg",))
    assert poison.SIG_CLOUDFLARE_IMAGES in verdict.signals


@pytest.mark.unit
def test_poison_price_and_vin_absence_context_dependent():
    # Only fires when the portal is asserted to always carry the field.
    no_ctx = poison.detect(_GOOD_HTML, price_present=False, vin_present=False)
    assert poison.SIG_PRICE_ABSENT not in no_ctx.signals
    with_ctx = poison.detect(
        _GOOD_HTML,
        portal_always_prices=True, price_present=False,
        portal_always_vins=True, vin_present=False,
    )
    assert poison.SIG_PRICE_ABSENT in with_ctx.signals
    assert poison.SIG_VIN_ABSENT in with_ctx.signals
    assert with_ctx.is_poison


@pytest.mark.unit
def test_poison_duplicate_body_signal():
    assert poison.SIG_DUPLICATE_BODY in poison.detect(_GOOD_HTML, is_duplicate_body=True).signals


@pytest.mark.unit
def test_body_hash_robust_to_wrapper_noise():
    a = "<html><body><p>identical honeypot prose</p></body></html>"
    b = '<html data-nonce="abc123"><body><p>identical   honeypot prose</p></body></html>'
    assert poison.body_hash(a) == poison.body_hash(b)


# ── WAF classifier (D1) ───────────────────────────────────────────────────────
@pytest.mark.unit
def test_waf_no_signals_is_inactive():
    verdict = waf.classify(status_code=200, headers={"content-type": "text/html"})
    assert verdict.vendor is waf.WafVendor.NONE
    assert not verdict.active
    assert verdict.level == "none"


@pytest.mark.unit
def test_waf_cloudflare_passive_on_200_is_medium():
    verdict = waf.classify(status_code=200, headers={"CF-Ray": "abc", "Server": "cloudflare"})
    assert verdict.vendor is waf.WafVendor.CLOUDFLARE
    assert verdict.active
    assert verdict.level == "medium"
    assert not verdict.challenge


@pytest.mark.unit
def test_waf_datadome_header():
    verdict = waf.classify(status_code=200, headers={"x-datadome-cid": "z"})
    assert verdict.vendor is waf.WafVendor.DATADOME


@pytest.mark.unit
def test_waf_akamai_cookie():
    verdict = waf.classify(status_code=200, headers={}, cookies={"ak_bmsc": "v", "_abck": "v"})
    assert verdict.vendor is waf.WafVendor.AKAMAI


@pytest.mark.unit
def test_waf_perimeterx_cookie():
    verdict = waf.classify(status_code=200, headers={}, cookies={"_pxhd": "v"})
    assert verdict.vendor is waf.WafVendor.PERIMETER_X


@pytest.mark.unit
def test_waf_403_without_vendor_is_high_unknown():
    verdict = waf.classify(status_code=403, headers={})
    assert verdict.active
    assert verdict.level == "high"
    assert verdict.challenge
    assert verdict.vendor is waf.WafVendor.UNKNOWN


@pytest.mark.unit
def test_waf_cloudflare_challenge_body_is_high():
    verdict = waf.classify(
        status_code=503,
        headers={"CF-Ray": "x"},
        body="<title>Just a moment...</title>",
    )
    assert verdict.vendor is waf.WafVendor.CLOUDFLARE
    assert verdict.level == "high"
    assert verdict.challenge


@pytest.mark.unit
def test_waf_datadome_captcha_body():
    verdict = waf.classify(
        status_code=403,
        headers={},
        body='<script src="https://captcha-delivery.com/c.js"></script>',
    )
    assert verdict.vendor is waf.WafVendor.DATADOME


@pytest.mark.unit
def test_waf_set_cookie_header_parsed():
    verdict = waf.classify(
        status_code=200,
        headers={"Set-Cookie": "datadome=abc; Path=/, other=1"},
    )
    assert verdict.vendor is waf.WafVendor.DATADOME


# ── schema-drift (D2) ─────────────────────────────────────────────────────────
@pytest.mark.unit
def test_schema_fingerprint_ignores_values_and_order():
    a = schema.schema_fingerprint({"make": "BMW", "model": "320d", "year": "2019"}, extraction_method="jsonld")
    b = schema.schema_fingerprint({"year": "2020", "model": "A4", "make": "Audi"}, extraction_method="jsonld")
    assert a == b  # same key-set + method → same fingerprint


@pytest.mark.unit
def test_schema_fingerprint_changes_with_keyset():
    a = schema.schema_fingerprint({"make": "BMW", "model": "320d"}, extraction_method="jsonld")
    b = schema.schema_fingerprint({"make": "BMW", "model": "320d", "vin": "x"}, extraction_method="jsonld")
    assert a != b


@pytest.mark.unit
def test_schema_fingerprint_ignores_empty_values():
    a = schema.schema_fingerprint({"make": "BMW", "model": "320d"}, extraction_method="jsonld")
    b = schema.schema_fingerprint({"make": "BMW", "model": "320d", "vin": ""}, extraction_method="jsonld")
    assert a == b  # empty vin is not a present field


@pytest.mark.unit
def test_check_drift_first_observation_inserts(conn):
    fp = schema.schema_fingerprint({"make": "BMW"}, extraction_method="jsonld")
    result = schema.check_drift(conn, "autoscout24.de", fp, "jsonld", now=1000)
    assert not result.changed
    assert result.old_fp is None
    row = conn.execute("SELECT sample_count, schema_fp FROM schema_registry WHERE portal=?", ("autoscout24.de",)).fetchone()
    assert row["sample_count"] == 1
    assert row["schema_fp"] == fp


@pytest.mark.unit
def test_check_drift_same_fp_bumps_sample(conn):
    fp = schema.schema_fingerprint({"make": "BMW"}, extraction_method="jsonld")
    schema.check_drift(conn, "autoscout24.de", fp, "jsonld", now=1000)
    result = schema.check_drift(conn, "autoscout24.de", fp, "jsonld", now=2000)
    assert not result.changed
    row = conn.execute("SELECT sample_count, verified_at FROM schema_registry WHERE portal=?", ("autoscout24.de",)).fetchone()
    assert row["sample_count"] == 2
    assert row["verified_at"] == 2000


@pytest.mark.unit
def test_check_drift_detects_change(conn):
    fp1 = schema.schema_fingerprint({"make": "BMW", "model": "x"}, extraction_method="jsonld")
    fp2 = schema.schema_fingerprint({"make": "BMW", "model": "x", "vin": "y"}, extraction_method="jsonld")
    schema.check_drift(conn, "autoscout24.de", fp1, "jsonld", now=1000)
    result = schema.check_drift(conn, "autoscout24.de", fp2, "jsonld", now=3000)
    assert result.changed
    assert result.old_fp == fp1
    assert result.new_fp == fp2
    row = conn.execute("SELECT schema_fp, last_change_at FROM schema_registry WHERE portal=?", ("autoscout24.de",)).fetchone()
    assert row["schema_fp"] == fp2
    assert row["last_change_at"] == 3000
