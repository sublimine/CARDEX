"""
Domain-resolution — candidate extraction + scoring (pure, no I/O).

Given a search-results page for "dealer name + city", pull the candidate domains,
drop the noise (search engines, social, marketplaces, business directories), and
score what's left so the most-likely dealer site is tried first. The actual
decision to persist is gated by a homepage VALIDATION (see ``validate.py``) — this
module only ranks; it never asserts a domain is the dealer.
"""
from __future__ import annotations

import re
import unicodedata
import urllib.parse

# Country → expected TLD (a country-TLD match is a positive signal, not a filter).
COUNTRY_TLD: dict[str, str] = {
    "DE": "de", "ES": "es", "CH": "ch", "NL": "nl", "BE": "be", "FR": "fr",
    "AT": "at", "IT": "it",
}

# Hosts that are never a dealer's own site: search engines, social, the tier-1
# marketplaces/aggregators, and business directories (they list the dealer but
# are not it). Substring match on the apex host.
_EXCLUDE: tuple[str, ...] = (
    # search / generic
    "duckduckgo", "mojeek", "bing.", "google", "googleusercontent", "startpage",
    "search.brave", "brave.com", "yahoo", "ecosia", "qwant", "yandex", "baidu",
    "searx", "searxng",
    # social / media
    "facebook", "instagram", "linkedin", "youtube", "twitter", "x.com", "tiktok",
    "pinterest", "mastodon", "reddit", "wikipedia", "wikimedia", "fandom",
    # marketplaces / aggregators (tier-1 + meta)
    "mobile.de", "autoscout24", "kleinanzeigen", "leboncoin", "lacentrale",
    "marktplaats", "2dehands", "2ememain", "gaspedaal", "milanuncios", "wallapop",
    "coches.net", "autotrader", "autoscout", "autohero", "heycar", "carvago",
    # business directories
    "gelbeseiten", "11880", "dasoertliche", "das-oertliche", "meinestadt",
    "pagesjaunes", "paginasamarillas", "qdq", "axesor", "einfo", "cylex",
    "local.ch", "search.ch", "goudengids", "pagesdor", "yelp", "trustpilot",
    "unternehmensauskunft", "cybo", "deutschebiz", "autos1000", "total-lokal",
    "bvmw", "northdata", "companyhouse", "kompass", "europages", "wlw.",
    "firmenabc", "moneyhouse", "zefix", "handelsregister", "infobel", "tuugo",
    "opendi", "yellowpages", "yellow.", "118712", "wer-zu-wem",
    "bedrijvenregister", "bedrijvenpagina", "bedrijven.", "telefoonboek",
    "drimble", "oozo.", "companyinfo", "kvk.nl", "kompass", "trendstop",
    "societe.com", "infogreffe", "verif.com", "axesor", "empresia", "expansion.com",
    "solocal", "browsehappy", "consentmanager", "cookiebot", "cookielaw",
    "localcities", "renovero", "swissmadesoftware", "dastelefonbuch", "tvg-verlag",
    "wipe.de", "adition", "surveymonkey", "apple.com", "kunze-medien",
    # infra / blogspam
    "blocksurvey", "buttondown", "amazon", "ebay", "wordpress.com", "wixsite",
    "blogspot", "medium.com", "github", "archive.org", "muw-nachrichten",
)

# Generic name tokens that don't distinguish a dealer (so a domain matching only
# these is NOT a name match). Mirrors name_to_domain._GENERIC + legal forms, plus
# the automotive/boilerplate nouns OEM locator dumps carry (ES "exposición y
# taller", NL "bedrijf", group words) — these matched unrelated workshops live.
_STOP: frozenset[str] = frozenset({
    "autohaus", "auto", "autos", "automobile", "automobiles", "automobil",
    "garage", "garages", "motors", "motor", "cars", "car", "gmbh", "co", "kg",
    "ag", "ohg", "ug", "se", "sa", "sarl", "sas", "srl", "sl", "bv", "nv", "sagl",
    "und", "the", "der", "die", "das", "van", "von", "de", "del", "vehicules",
    "fahrzeuge", "fahrzeug", "zweig", "nl", "zw", "concessionnaire", "occasion",
    "of", "and", "et", "y",
    # ES / generic automotive nouns (boilerplate, not identity)
    "taller", "talleres", "exposicion", "exposiciones", "automocion", "automocio",
    "vehiculos", "vehiculo", "concesionario", "concesionarios", "concesionari",
    "servicio", "servicios", "recambios", "ocasion", "seminuevos", "seminuevo",
    "comercial", "werkstatt", "carrosserie", "bedrijf", "handel", "handels",
    # group / center words across languages
    "grupo", "group", "groupe", "gruppe", "groep", "centro", "center", "centre",
    "zentrum",
})

# Marque names: never distinctive of a *dealer* (every Toyota dealer's page says
# "Toyota"). A real dealer always carries a non-brand token too, so dropping these
# only removes brand-coincidence matches — strictly safe.
_BRANDS: frozenset[str] = frozenset({
    "toyota", "skoda", "audi", "seat", "opel", "ford", "fiat", "mini", "jeep",
    "volkswagen", "peugeot", "renault", "citroen", "nissan", "hyundai",
    "mercedes", "mazda", "honda", "volvo", "dacia", "cupra", "porsche",
    "jaguar", "lexus", "suzuki", "mitsubishi", "subaru", "tesla", "chevrolet",
    "chrysler", "lancia", "smart", "isuzu", "ssangyong", "alfa", "romeo",
})


def _norm(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", (s or "").lower())
        if not unicodedata.combining(c)
    )


# Boilerplate that pollutes a dealer name: parentheticals "(Zaragoza - …)" and a
# trailing " - <descriptor>" ("- Exposición y Taller"), common in OEM locator dumps.
_PAREN_RE = re.compile(r"\([^)]*\)")
_DESC_RE = re.compile(r"\s+-\s+.*$")


def clean_name(name: str) -> str:
    """Strip OEM-locator boilerplate: parentheticals + trailing ' - descriptor'."""
    s = _PAREN_RE.sub(" ", name or "")
    s = _DESC_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def name_tokens(name: str) -> list[str]:
    """Distinctive tokens of a dealer name (lowercased, unaccented, stopwords/brands out)."""
    n = re.sub(r"[^a-z0-9\s]", " ", _norm(clean_name(name)))
    return [t for t in n.split() if len(t) >= 4 and t not in _STOP and t not in _BRANDS]


# An embedded TLD before the real one ("jobs.bortolin.net.bmw.be") = a concatenation
# artifact from a search result, not a real host → reject.
_EMBEDDED_TLD_RE = re.compile(
    r"\.(?:com|net|org|info|biz|de|fr|es|ch|nl|be|it|at|eu|co)\.", re.I
)


def _is_malformed(host: str) -> bool:
    return host.count(".") > 3 or bool(_EMBEDDED_TLD_RE.search(host))


def apex(host_or_url: str) -> str | None:
    """Bare host (no www., no scheme/path), or None if absent/malformed."""
    s = host_or_url.strip()
    if "://" not in s:
        s = "https://" + s
    host = urllib.parse.urlparse(s).netloc.lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host or _is_malformed(host):
        return None
    return host


def is_excluded(host: str) -> bool:
    h = (host or "").lower()
    return any(x in h for x in _EXCLUDE)


# Free / ISP / webmail providers: an email hosted there is NOT the dealer's own
# domain. A dealer publishing info@gmx.de tells us nothing about its website.
_FREEMAIL: frozenset[str] = frozenset({
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.fr", "hotmail.de",
    "hotmail.es", "hotmail.it", "outlook.com", "outlook.de", "outlook.fr",
    "outlook.es", "live.com", "live.fr", "live.de", "live.nl", "yahoo.com",
    "yahoo.fr", "yahoo.de", "yahoo.es", "yahoo.it", "ymail.com", "aol.com",
    "icloud.com", "me.com", "mac.com", "mail.com", "email.com",
    "gmx.de", "gmx.net", "gmx.ch", "gmx.at", "web.de", "t-online.de",
    "freenet.de", "arcor.de", "protonmail.com", "proton.me", "tutanota.com",
    # ISPs by country (CH/FR/BE/NL/ES/IT)
    "bluewin.ch", "sunrise.ch", "hispeed.ch", "green.ch", "swissonline.ch",
    "orange.fr", "wanadoo.fr", "free.fr", "sfr.fr", "laposte.net", "neuf.fr",
    "bbox.fr", "numericable.fr", "telenet.be", "skynet.be", "proximus.be",
    "scarlet.be", "voo.be", "belgacom.net", "ziggo.nl", "kpnmail.nl",
    "planet.nl", "home.nl", "telfort.nl", "hetnet.nl", "chello.nl", "xs4all.nl",
    "telefonica.net", "terra.es", "movistar.es", "ya.com", "wanadoo.es",
    "libero.it", "tin.it", "alice.it", "virgilio.it",
})


def email_apex(email: str) -> str | None:
    """
    The apex domain of an email address — a zero-cost candidate domain — or None if
    the address is freemail/ISP/a directory/malformed. The dealer published this
    address itself, so the apex is strong (but still homepage-validated) provenance.
    """
    if not email or "@" not in email:
        return None
    host = email.rsplit("@", 1)[-1].strip().lower().rstrip(".")
    a = apex(host)
    if not a or a in _FREEMAIL or is_excluded(a):
        return None
    return a


_UDDG_RE = re.compile(r"uddg=([^\"&]+)")
_HREF_RE = re.compile(r'href="(https?://[^"]+)"', re.I)


def extract_candidates(html: str) -> list[str]:
    """
    Ordered, de-duped candidate apex domains from a search-results page.

    Handles DuckDuckGo's ``uddg=`` redirect param first (its real result links),
    then any absolute href. Excluded hosts are dropped. Order = result order, so
    the search engine's own ranking is preserved as a tiebreaker.
    """
    urls: list[str] = []
    for m in _UDDG_RE.finditer(html):
        urls.append(urllib.parse.unquote(m.group(1)))
    for m in _HREF_RE.finditer(html):
        urls.append(m.group(1))
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        h = apex(u)
        if h and h not in seen and not is_excluded(h):
            seen.add(h)
            out.append(h)
    return out


def score(host: str, name: str, country: str, rank: int) -> float:
    """
    Heuristic confidence a candidate host is the dealer (0..1-ish), pre-validation.

    +0.6 a distinctive name token appears in the host (ungeheuer→ungeheuer-bmw.de)
    +0.2 country TLD matches · +0.2/(rank+1) search-rank prior. Never decisive on
    its own — ``validate.py`` confirms before persisting; this only orders attempts.
    """
    h = _norm(host)
    s = 0.0
    toks = name_tokens(name)
    if any(t in h for t in toks):
        s += 0.6
    tld = COUNTRY_TLD.get((country or "").upper())
    if tld and h.endswith("." + tld):
        s += 0.2
    s += 0.2 / (rank + 1)
    # Prefer the dealer's OWN apex (bilia.be) over an OEM dealer-locator subdomain
    # (bilia.bmw.be): a 3+-label host is usually a brand/portal-hosted page. Mild
    # penalty — still accepted if it is the only candidate.
    if h.count(".") >= 2:
        s -= 0.15
    return round(s, 3)


def ranked_candidates(html: str, name: str, country: str, top: int = 4) -> list[tuple[str, float]]:
    """Top candidate (host, score) pairs from a search page, best first."""
    cands = extract_candidates(html)
    scored = [(h, score(h, name, country, i)) for i, h in enumerate(cands)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top]
