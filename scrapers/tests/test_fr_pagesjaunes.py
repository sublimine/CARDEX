"""
Unit tests for fr_pagesjaunes pure parsers (no network, no DB).

Fixtures are derived from REAL PagesJaunes.fr HTML (dept=75, page=1)
verified 2026-06-07.

Run from the scrapers/ directory:
    cd scrapers && PYTHONPATH=.. python -m pytest tests/test_fr_pagesjaunes.py -q
"""
from __future__ import annotations

import base64
import json
import textwrap

import pytest

from scrapers.discovery.sources.fr_pagesjaunes import (
    _decode_b64,
    _domain,
    _normalize_url,
    _parse_bi_block,
    parse_listing_page,
    parse_total_results,
    pages_for_count,
    _DEPARTMENTS,
)


# ---------------------------------------------------------------------------
# Helpers to build realistic fixtures
# ---------------------------------------------------------------------------

def _b64(url: str) -> str:
    """Encode a URL to PagesJaunes base64 (no padding)."""
    return base64.b64encode(url.encode()).decode().rstrip("=")


def _make_bi_block(
    code_etab: str = "08401421",
    name: str = "AUDI Premium Automobiles",
    address: str = "105 boulevard Murat 75016 Paris",
    website_url: str | None = None,
    pos: int = 1,
) -> str:
    """Build a minimal but realistic PagesJaunes ``<li id="bi-CODE">`` block."""
    # Website link with base64 URL (optional)
    website_section = ""
    if website_url:
        b64 = _b64(website_url)
        website_section = f"""
        <a class="bi-website pj-lb pj-link" data-pjlb='{{"url":"{b64}","ucod":"b64u8"}}'
           href="#">Voir le site web</a>
        """

    # Detail URL for denomination link
    detail_b64 = _b64(f"/pros/detail?code_etablissement={code_etab}&code_localite=L07505600&code_rubrique=061240")

    return textwrap.dedent(f"""\
        <li id="bi-{code_etab}" class="bi bi-generic bi-propay">
          <span class="ancre-google" id="epj-{code_etab}"></span>
          <div class="bi-content">
            <div class="bi-header-title">
              <a class="bi-denomination pj-link" href="/pros/{code_etab}"
                 data-pjlb='{{"url":"{detail_b64}","ucod":"b64u8"}}'>
                <h3 class="truncate-2-lines">{name}</h3>
              </a>
            </div>
            <div class="bi-address small">
              <a href="#" class="pj-lb pj-link">
                {address}
                <span class="label-adresse">Voir le plan</span>
              </a>
            </div>
            {website_section}
            <div class="bi-ctas">
              <button data-pjajax='{{"url":"/annuaire/ajax/phone_number?id={code_etab}&identifier={code_etab}"}}'
                      class="button btn btn_primary btn_tel">
                Afficher le N°
              </button>
            </div>
          </div>
        </li>
    """)


def _make_page(blocks: list[str], total_results: int = 20) -> str:
    """Wrap bi blocks in a minimal PagesJaunes page HTML."""
    bi_list = "\n".join(blocks)
    return textwrap.dedent(f"""\
        <html><body>
        <span id="SEL-nbresultat">{total_results}</span>
        <ul class="bi-list">
        {bi_list}
        </ul>
        </body></html>
    """)


# ---------------------------------------------------------------------------
# Constants from real live page (verified 2026-06-07)
# ---------------------------------------------------------------------------

# Real dealer from dept 75 page 1
_CODE_AUDI = "08401421"
_CODE_PEUGEOT = "61833418"

# Real website URL found in dept 75 data (~12% have website in listing)
_CITROENPARIS_URL = "http://www.citroenparis20.fr"
_CITROENPARIS_B64 = _b64(_CITROENPARIS_URL)


# ---------------------------------------------------------------------------
# _decode_b64
# ---------------------------------------------------------------------------

class TestDecodeB64:
    def test_standard_url(self):
        b64 = _b64("https://www.example.fr/")
        assert _decode_b64(b64) == "https://www.example.fr/"

    def test_real_citroenparis_url(self):
        decoded = _decode_b64(_CITROENPARIS_B64)
        assert decoded == _CITROENPARIS_URL

    def test_padding_tolerance(self):
        raw = _b64("https://www.autohaus.de/page")
        no_pad = raw.rstrip("=")
        assert _decode_b64(no_pad) == _decode_b64(raw)

    def test_empty_returns_none(self):
        assert _decode_b64("") is None

    def test_none_returns_none(self):
        assert _decode_b64(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _normalize_url
# ---------------------------------------------------------------------------

class TestNormalizeUrl:
    def test_http_url_kept(self):
        assert _normalize_url("http://www.example.fr") == "http://www.example.fr"

    def test_trailing_slash_stripped(self):
        assert _normalize_url("https://example.fr/") == "https://example.fr"

    def test_pagesjaunes_filtered(self):
        assert _normalize_url("https://www.pagesjaunes.fr/pros/12345") is None

    def test_solocal_filtered(self):
        assert _normalize_url("https://www.solocal.com/landing/inscription") is None

    def test_javascript_filtered(self):
        assert _normalize_url("javascript:void(0)") is None

    def test_none_returns_none(self):
        assert _normalize_url(None) is None


# ---------------------------------------------------------------------------
# _domain
# ---------------------------------------------------------------------------

class TestDomain:
    def test_strips_www(self):
        assert _domain("http://www.citroenparis20.fr") == "citroenparis20.fr"

    def test_no_www(self):
        assert _domain("https://autohaus-exemple.fr") == "autohaus-exemple.fr"

    def test_none(self):
        assert _domain(None) is None


# ---------------------------------------------------------------------------
# _parse_bi_block
# ---------------------------------------------------------------------------

class TestParseBiBlock:
    def test_basic_no_website(self):
        block = _make_bi_block(code_etab=_CODE_AUDI, name="AUDI Premium Automobiles",
                                address="105 boulevard Murat 75016 Paris")
        c = _parse_bi_block(block)
        assert c is not None
        assert c["registry_id"] == f"pj-{_CODE_AUDI}"
        assert c["name"] == "AUDI Premium Automobiles"
        assert c["source"] == "pagesjaunes"
        assert c["country"] == "FR"
        assert c["source_layer"] == 2
        assert c["domain"] is None
        assert c["url"] is None

    def test_address_extracted_and_cleaned(self):
        block = _make_bi_block(address="105 boulevard Murat 75016 Paris")
        c = _parse_bi_block(block)
        assert c is not None
        addr = c["address"] or ""
        assert "105 boulevard Murat" in addr
        assert "75016" in addr
        # "Voir le plan" must be stripped
        assert "Voir le plan" not in addr

    def test_with_website(self):
        block = _make_bi_block(
            code_etab="12345678",
            name="Citroën Paris 20",
            website_url=_CITROENPARIS_URL,
        )
        c = _parse_bi_block(block)
        assert c is not None
        assert c["url"] == _CITROENPARIS_URL
        assert c["domain"] == "citroenparis20.fr"

    def test_external_refs_contain_detail_url(self):
        block = _make_bi_block(code_etab=_CODE_AUDI)
        c = _parse_bi_block(block)
        refs = c.get("external_refs") or {}
        assert "pj_detail" in refs
        assert _CODE_AUDI in refs["pj_detail"]

    def test_missing_id_returns_none(self):
        block = "<li class='bi bi-generic'><h3>No ID here</h3></li>"
        assert _parse_bi_block(block) is None

    def test_pj_website_url_filtered(self):
        """A data-pjlb that decodes to a pagesjaunes.fr URL must not become domain."""
        pj_b64 = _b64("/pros/detail?code_etablissement=12345")
        block = textwrap.dedent(f"""\
            <li id="bi-99999999" class="bi bi-generic">
              <h3>Garage Test</h3>
              <a class="bi-website" data-pjlb='{{"url":"{pj_b64}","ucod":"b64u8"}}'></a>
            </li>
        """)
        c = _parse_bi_block(block)
        assert c is not None
        assert c["domain"] is None


# ---------------------------------------------------------------------------
# parse_listing_page
# ---------------------------------------------------------------------------

class TestParseListingPage:
    def test_two_dealers_no_web(self):
        b1 = _make_bi_block(code_etab=_CODE_AUDI, name="AUDI Premium Automobiles")
        b2 = _make_bi_block(code_etab=_CODE_PEUGEOT, name="Peugeot Groult Auto Service")
        page = _make_page([b1, b2], total_results=326)
        candidates = parse_listing_page(page)
        assert len(candidates) == 2
        codes = {c["registry_id"] for c in candidates}
        assert f"pj-{_CODE_AUDI}" in codes
        assert f"pj-{_CODE_PEUGEOT}" in codes

    def test_one_with_website(self):
        b1 = _make_bi_block(code_etab=_CODE_AUDI, website_url=_CITROENPARIS_URL)
        b2 = _make_bi_block(code_etab=_CODE_PEUGEOT)
        page = _make_page([b1, b2])
        candidates = parse_listing_page(page)
        with_web = [c for c in candidates if c["domain"]]
        without_web = [c for c in candidates if not c["domain"]]
        assert len(with_web) == 1
        assert len(without_web) == 1
        assert with_web[0]["domain"] == "citroenparis20.fr"

    def test_empty_page_returns_empty(self):
        assert parse_listing_page("<html><body></body></html>") == []

    def test_all_required_fields_present(self):
        b = _make_bi_block()
        page = _make_page([b])
        c = parse_listing_page(page)[0]
        for field in ("domain", "country", "source_layer", "source", "url",
                      "name", "address", "city", "postcode", "phone", "email",
                      "lat", "lng", "registry_id", "external_refs"):
            assert field in c, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# parse_total_results / pages_for_count
# ---------------------------------------------------------------------------

class TestParseTotalResults:
    def test_real_paris_count(self):
        html = '<span id="SEL-nbresultat">326</span>'
        assert parse_total_results(html) == 326

    def test_zero_when_not_found(self):
        assert parse_total_results("<html></html>") == 0


class TestPagesForCount:
    def test_exact_multiple(self):
        assert pages_for_count(40) == 2

    def test_partial_page(self):
        assert pages_for_count(21) == 2

    def test_single_page(self):
        assert pages_for_count(15) == 1

    def test_zero_results(self):
        assert pages_for_count(0) == 1

    def test_326_results(self):
        # Paris has 326 → ceil(326/20) = 17 pages
        assert pages_for_count(326) == 17


# ---------------------------------------------------------------------------
# Department list
# ---------------------------------------------------------------------------

class TestDepartments:
    def test_exactly_96(self):
        assert len(_DEPARTMENTS) == 96

    def test_contains_2a_2b(self):
        assert "2A" in _DEPARTMENTS
        assert "2B" in _DEPARTMENTS

    def test_starts_with_01(self):
        assert _DEPARTMENTS[0] == "01"

    def test_contains_95(self):
        assert "95" in _DEPARTMENTS

    def test_no_dom_tom_by_default(self):
        # DOM-TOM codes are 971-976; should not be in the list
        for code in ["971", "972", "973", "974", "975", "976"]:
            assert code not in _DEPARTMENTS
