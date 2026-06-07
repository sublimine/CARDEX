"""Domain-resolution pure core — candidate ranking + homepage validation (no network)."""
from __future__ import annotations

import asyncio

import pytest

from scrapers.discovery.domain_resolution import candidate as C
from scrapers.discovery.domain_resolution.validate import confirms_dealer, validate_domain


# ── candidate ───────────────────────────────────────────────────────────────────
@pytest.mark.unit
def test_name_tokens_drops_generic_and_short():
    toks = C.name_tokens("Autohaus Richard Hable GmbH")
    assert "hable" in toks and "richard" in toks
    assert "autohaus" not in toks and "gmbh" not in toks   # generic / legal form


@pytest.mark.unit
def test_clean_name_strips_oem_boilerplate():
    assert C.clean_name("ARTAL VEHÍCULOS ZARAGOZA, S.L. (Zaragoza - Añes) - Exposición y Taller") \
        == "ARTAL VEHÍCULOS ZARAGOZA, S.L."
    assert C.clean_name("ASTURHIBRIDO, S.L. (Gijón) - Exposición y Taller") == "ASTURHIBRIDO, S.L."
    assert C.clean_name("AH Stöber Eschwege GmbH & Co. KG") == "AH Stöber Eschwege GmbH & Co. KG"


@pytest.mark.unit
def test_name_tokens_drops_brands_and_es_generics():
    # the live poison: "Taller"/"Exposición"/"Toyota" must NOT be distinctive tokens
    toks = C.name_tokens("ASTURHIBRIDO, S.L. (Gijón) - Exposición y Taller")
    assert toks == ["asturhibrido"]                       # gijon is in (), stripped; rest generic
    assert "taller" not in C.name_tokens("Talleres Joan Carles")  # generic noun out
    assert "toyota" not in C.name_tokens("Toyota Igualada")       # brand out
    assert "armentia" in C.name_tokens("Autocentro Armentia Toyota")  # real token kept


@pytest.mark.unit
def test_apex_strips_www_scheme_path():
    assert C.apex("https://www.ungeheuer-bmw.de/occasionen") == "ungeheuer-bmw.de"
    assert C.apex("ungeheuer-bmw.de") == "ungeheuer-bmw.de"
    assert C.apex("not a url") is None


@pytest.mark.unit
def test_is_excluded_blocks_aggregators_social_directories():
    for h in ("mobile.de", "www.autoscout24.ch", "facebook.com", "gelbeseiten.de",
              "local.ch", "duckduckgo.com", "wikipedia.org", "unternehmensauskunft.com"):
        assert C.is_excluded(h), h
    assert not C.is_excluded("ungeheuer-bmw.de")
    assert not C.is_excluded("bmw-hable.de")


@pytest.mark.unit
def test_is_excluded_blocks_business_directories_per_country():
    # live false positive: bedrijvenregister.nl (NL business directory) passed
    # validation because directory pages echo the dealer name + automotive words.
    for h in ("bedrijvenregister.nl", "www.telefoonboek.nl", "drimble.nl", "oozo.nl",
              "kvk.nl", "societe.com", "infogreffe.fr", "verif.com", "empresia.es",
              "kompass.com", "trendstop.be"):
        assert C.is_excluded(h), h
    assert not C.is_excluded("garagecupido.nl")   # real dealer must still pass


@pytest.mark.unit
def test_extract_candidates_ddg_uddg_and_excludes():
    import urllib.parse as up
    real = up.quote("https://www.ungeheuer-bmw.de/", safe="")
    spam = up.quote("https://facebook.com/ungeheuer", safe="")
    html = (f'<a class="result__a" href="//duckduckgo.com/l/?uddg={real}">Ungeheuer</a>'
            f'<a href="//duckduckgo.com/l/?uddg={spam}">FB</a>'
            '<a href="https://gelbeseiten.de/x">dir</a>')
    cands = C.extract_candidates(html)
    assert "ungeheuer-bmw.de" in cands
    assert "facebook.com" not in cands and "gelbeseiten.de" not in cands


@pytest.mark.unit
def test_score_rewards_name_token_and_country_tld():
    # name token present + .de TLD + rank 0 → high
    s_good = C.score("ungeheuer-bmw.de", "Ungeheuer Automobile", "DE", 0)
    s_meh = C.score("emilfrey.de", "Ungeheuer Automobile", "DE", 1)   # no name token
    assert s_good > s_meh
    assert C.score("hable-cars.de", "Autohaus Richard Hable", "DE", 0) >= 0.8  # token+tld+rank


@pytest.mark.unit
def test_ranked_candidates_orders_best_first():
    import urllib.parse as up
    a = up.quote("https://emilfrey.de/", safe="")          # rank0, no token
    b = up.quote("https://ungeheuer-bmw.de/", safe="")     # rank1, token+tld
    html = f'<a href="//x/?uddg={a}">a</a><a href="//x/?uddg={b}">b</a>'
    ranked = C.ranked_candidates(html, "Ungeheuer Automobile", "DE")
    assert ranked[0][0] == "ungeheuer-bmw.de"              # token beats rank prior


# ── validate ──────────────────────────────────────────────────────────────────
_DEALER_HOME = (
    "<html><head><title>Autohaus Hable — Ihr BMW Partner in Grafenau</title></head>"
    "<body><h1>Willkommen bei Autohaus Richard Hable in Grafenau</h1>"
    "<p>Neuwagen, Gebrauchtwagen und Fahrzeuge aller Art. Werkstatt & Service.</p>"
    "</body></html>"
)


@pytest.mark.unit
def test_confirms_dealer_name_plus_auto():
    ok, why = confirms_dealer(_DEALER_HOME, "Autohaus Richard Hable", "Grafenau")
    assert ok and why in ("name+auto", "city+auto")


_FILLER = "<p>" + ("Lorem ipsum dolor sit amet consectetur adipiscing elit. " * 8) + "</p>"


@pytest.mark.unit
def test_confirms_dealer_rejects_without_auto_signal():
    html = ("<html><body><h1>Hable Immobilien Grafenau</h1>"
            "<p>Wohnungen und Häuser zu verkaufen.</p>" + _FILLER + "</body></html>")
    ok, why = confirms_dealer(html, "Autohaus Richard Hable", "Grafenau")
    assert not ok and why == "no_automotive_signal"


@pytest.mark.unit
def test_confirms_dealer_rejects_namesake_elsewhere():
    html = ("<html><body><h1>Müller Bäckerei Konditorei</h1>"
            "<p>frisches Brot und Kuchen.</p>" + _FILLER + "</body></html>")
    ok, why = confirms_dealer(html, "Autohaus Richard Hable", "Grafenau")
    assert not ok and why == "name_not_on_page"


@pytest.mark.unit
def test_confirms_dealer_requires_name_when_distinctive():
    # live false positive: "ASTURHIBRIDO (Gijón) - Exposición y Taller" matched an
    # unrelated Gijón workshop via city+auto alone. With a distinctive name present,
    # the city is NOT enough — the name must appear on the page.
    page = ("<html><body><h1>Talleres Piñera — Reparación de vehículos en Gijón</h1>"
            "<p>Taller mecánico y carrocería. Coches y furgonetas.</p>"
            + _FILLER + "</body></html>")
    ok, why = confirms_dealer(page, "ASTURHIBRIDO, S.L. (Gijón) - Exposición y Taller", "Gijón")
    assert not ok and why == "name_not_on_page"


@pytest.mark.unit
def test_confirms_dealer_city_fallback_only_when_name_generic():
    # name made entirely of generic/brand tokens → no distinctive token → city
    # confirmation is allowed (this is the only path city-alone may succeed).
    page = ("<html><body><h1>Concesionario Toyota en Igualada</h1>"
            "<p>Venta de vehículos nuevos y de ocasión. Taller propio.</p>"
            + _FILLER + "</body></html>")
    assert C.name_tokens("Concesionario Toyota - Exposición y Taller") == []  # all generic/brand
    ok, why = confirms_dealer(page, "Concesionario Toyota - Exposición y Taller", "Igualada")
    assert ok and why == "city+auto"


@pytest.mark.unit
def test_confirms_dealer_empty_page():
    ok, why = confirms_dealer("", "X", "Y")
    assert not ok and why == "empty_page"


@pytest.mark.unit
def test_validate_domain_with_injected_fetcher_ok():
    class _Resp:
        status_code = 200
        text = _DEALER_HOME

    async def fetcher(url):
        return _Resp()

    ok, why = asyncio.run(validate_domain("bmw-hable.de", "Autohaus Richard Hable", "Grafenau", fetcher))
    assert ok


@pytest.mark.unit
def test_validate_domain_404_and_fetch_error_not_confirmed():
    class _R404:
        status_code = 404
        text = ""

    async def f404(url):
        return _R404()

    async def boom(url):
        raise ConnectionError("down")

    assert asyncio.run(validate_domain("x.de", "X", "Y", f404)) == (False, "http_404")
    ok, why = asyncio.run(validate_domain("x.de", "X", "Y", boom))
    assert not ok and why.startswith("fetch_error")


@pytest.mark.unit
def test_apex_rejects_malformed_embedded_tld_host():
    # the live false positive: "jobs.bortolin.net.bmw.be" (embedded .net. + 5 labels)
    assert C.apex("https://jobs.bortolin.net.bmw.be/") is None
    assert C.apex("https://a.b.c.d.e.de/") is None          # too many labels
    assert C.apex("https://bilia.bmw.be/") == "bilia.bmw.be"  # legit 3-label subdomain OK


@pytest.mark.unit
def test_score_prefers_own_apex_over_oem_subdomain():
    own = C.score("bilia.be", "Bilia Arlon", "BE", 1)         # 2-label own domain
    oem = C.score("bilia.bmw.be", "Bilia Arlon", "BE", 0)     # OEM subdomain, better rank
    assert own > oem                                          # own apex wins despite worse rank
