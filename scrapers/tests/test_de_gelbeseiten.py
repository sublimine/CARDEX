"""
Unit tests for de_gelbeseiten pure parsers (no network, no DB).

Run from the scrapers/ directory:
    cd scrapers && PYTHONPATH=.. python -m pytest tests/test_de_gelbeseiten.py -q
"""
import base64
import textwrap

import pytest

from scrapers.discovery.sources.de_gelbeseiten import (
    _decode_b64,
    _domain,
    _extract_address_from_maps,
    _normalize_url,
    parse_article,
    parse_html_page,
)


# ---------------------------------------------------------------------------
# Fixtures built from REAL captured HTML (verified 2026-06-07)
# ---------------------------------------------------------------------------

def _b64(url: str) -> str:
    """Encode a URL to GelbeSeiten base64 (no padding)."""
    return base64.b64encode(url.encode()).decode().rstrip("=")


# Real UUID from the live listing (first article on page 1)
_UUID_FROHN = "2953b651-ea90-49b3-ae4e-186c2a998c3e"
_URL_FROHN = "https://www.auto-frohn.de/"
_WEB_FROHN = _b64(_URL_FROHN)

# Maps address for Frohn (base64-encoded)
_MAPS_FROHN_URL = "https://www.google.com/maps/place/Dieselstr. 2, 44805 Bochum"
_MAPS_FROHN_B64 = _b64(_MAPS_FROHN_URL)

# Phone base64 (as seen in real HTML)
_PHONE_B64 = _b64("0234 8 57 51")


def _make_article(
    uuid: str = _UUID_FROHN,
    name: str = "Autohaus Friedrich Frohn GmbH &amp; Co. KG",
    web_b64: str | None = _WEB_FROHN,
    maps_b64: str | None = _MAPS_FROHN_B64,
    phone: str | None = "0234 8 57 51",
) -> str:
    """Build a minimal but realistic <article> fixture."""
    web_attr = f'data-webseiteLink="{web_b64}"' if web_b64 else ""
    maps_btn = (
        f'<button data-prg="{maps_b64}">Route</button>'
        if maps_b64
        else ""
    )
    phone_span = (
        f'<span class="mod-TelefonnummerKompakt">{phone}</span>'
        if phone
        else ""
    )
    return textwrap.dedent(f"""\
        <article class="mod mod-Treffer"
                 id="treffer_161096112901"
                 data-realid="{uuid}" data-teilnehmerid="161096112901">
          <a href="https://www.gelbeseiten.de/gsbiz/{uuid}"
             data-realid="{uuid}">
            <h2 class="mod-Treffer__name" data-wipe-name="Titel">{name}</h2>
          </a>
          <div class="mod-Treffer__buttonleiste">
            <button {web_attr}>Website</button>
            {maps_btn}
            {phone_span}
          </div>
        </article>
    """)


# ---------------------------------------------------------------------------
# _decode_b64
# ---------------------------------------------------------------------------

class TestDecodeB64:
    def test_standard_url(self):
        b64 = _b64("https://www.example.de/")
        assert _decode_b64(b64) == "https://www.example.de/"

    def test_frohn_real_b64(self):
        assert _decode_b64(_WEB_FROHN) == _URL_FROHN.rstrip("/") or \
               _decode_b64(_WEB_FROHN).startswith("https://www.auto-frohn.de")

    def test_padding_tolerance(self):
        # GelbeSeiten omits base64 padding; function must handle it
        raw = "aHR0cHM6Ly93d3cuYXV0by1mcm9obi5kZS8="  # with padding
        no_pad = raw.rstrip("=")
        assert _decode_b64(no_pad) == _decode_b64(raw)

    def test_empty_returns_none(self):
        assert _decode_b64("") is None

    def test_none_returns_none(self):
        assert _decode_b64(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _domain
# ---------------------------------------------------------------------------

class TestDomain:
    def test_strips_www(self):
        assert _domain("https://www.auto-frohn.de/") == "auto-frohn.de"

    def test_already_no_www(self):
        assert _domain("https://autohaus-xyz.de") == "autohaus-xyz.de"

    def test_none_input(self):
        assert _domain(None) is None

    def test_empty_input(self):
        assert _domain("") is None


# ---------------------------------------------------------------------------
# _extract_address_from_maps
# ---------------------------------------------------------------------------

class TestExtractAddressFromMaps:
    def test_real_frohn_address(self):
        art = _make_article(maps_b64=_MAPS_FROHN_B64)
        addr = _extract_address_from_maps(art)
        assert addr is not None
        assert "Dieselstr" in addr
        assert "44805" in addr

    def test_no_maps_button_returns_none(self):
        art = _make_article(maps_b64=None)
        addr = _extract_address_from_maps(art)
        assert addr is None


# ---------------------------------------------------------------------------
# parse_article
# ---------------------------------------------------------------------------

class TestParseArticle:
    def test_full_article_with_web(self):
        art = _make_article()
        c = parse_article(art)
        assert c is not None
        assert c["registry_id"] == _UUID_FROHN
        assert c["domain"] == "auto-frohn.de"
        assert c["url"] is not None and "auto-frohn.de" in c["url"]
        assert c["name"] is not None and "Frohn" in c["name"]
        assert c["source"] == "gelbeseiten"
        assert c["country"] == "DE"
        assert c["source_layer"] == 2

    def test_article_without_website(self):
        art = _make_article(web_b64=None)
        c = parse_article(art)
        assert c is not None
        assert c["registry_id"] == _UUID_FROHN
        assert c["domain"] is None
        assert c["url"] is None

    def test_article_missing_uuid_returns_none(self):
        # Construct an article with no data-realid and no gsbiz href
        art = "<article><h2 class='mod-Treffer__name'>Test</h2></article>"
        assert parse_article(art) is None

    def test_external_refs_contains_listing_url(self):
        art = _make_article()
        c = parse_article(art)
        assert "listing" in c["external_refs"]
        assert _UUID_FROHN in c["external_refs"]["listing"]

    def test_html_entities_in_name_unescaped(self):
        art = _make_article(name="GmbH &amp; Co. KG")
        c = parse_article(art)
        assert "&amp;" not in (c["name"] or "")
        assert "&" in (c["name"] or "")

    def test_address_extracted(self):
        art = _make_article()
        c = parse_article(art)
        assert c["address"] is not None
        assert "Dieselstr" in c["address"]

    def test_different_uuid(self):
        other_uuid = "6881562b-0e50-4e8d-af33-0555bac69095"
        art = _make_article(uuid=other_uuid)
        c = parse_article(art)
        assert c["registry_id"] == other_uuid


# ---------------------------------------------------------------------------
# parse_html_page
# ---------------------------------------------------------------------------

class TestParseHtmlPage:
    def test_two_articles_deduped_pinned(self):
        """A 'pinned' sponsor that appears twice must be deduplicated."""
        art1 = _make_article(uuid=_UUID_FROHN)
        other_uuid = "6881562b-0e50-4e8d-af33-0555bac69095"
        art2 = _make_article(uuid=other_uuid)
        # Pinned: art1 appears twice
        page = art1 + art2 + art1
        candidates = parse_html_page(page)
        assert len(candidates) == 2
        ids = {c["registry_id"] for c in candidates}
        assert _UUID_FROHN in ids
        assert other_uuid in ids

    def test_empty_page(self):
        assert parse_html_page("<html><body></body></html>") == []

    def test_article_without_uuid_skipped(self):
        bad_art = "<article><h2 class='mod-Treffer__name'>NoUUID</h2></article>"
        good_art = _make_article()
        candidates = parse_html_page(bad_art + good_art)
        assert len(candidates) == 1

    def test_with_web_ratio(self):
        """At least some articles should have a domain when web_b64 is set."""
        arts = "".join(_make_article(uuid=f"{'a'*8}-{'b'*4}-{'c'*4}-{'d'*4}-{str(i).zfill(12)}") for i in range(5))
        candidates = parse_html_page(arts)
        with_web = [c for c in candidates if c["domain"]]
        assert len(with_web) == 5
