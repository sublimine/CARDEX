"""
OEM dealer-locator discovery — config-driven multi-brand sweep.

Every major OEM publishes its authorised dealer network through a public locator
backend (the same JSON the brand's "find a dealer" page consumes). These are
coste-cero discovery sources that, crucially, often carry the **dealer's own
website** — the bridge from discovery to inventory (E01/E03 on the dealer site).

This module generalises the single-brand `oem_bmw.py` blueprint into a
config-driven sweep over the brands whose locator is a clean public endpoint,
VERIFIED live (curl) on 2026-06-07 from a residential IP:

  brand     shape                         countries (verified counts, single call)
  ───────   ───────────────────────────   ───────────────────────────────────────
  vw        oneapi.volkswagen.com SDS      DE1903 FR417 ES264 NL121 CH174  (BE→204)
  audi      same SDS, tenant a-*           DE1233 FR219 ES193 NL77 BE64 CH95
  skoda     /apps/retailers GetDealers     DE442 FR118 ES67 NL113 BE87 CH117
  toyota    dealersAutoSuggestion          DE511 FR337 ES226 NL110 BE98 CH144
  hyundai   SSR data-js-content / Uberall  DE498 FR197 ES175 NL66 BE74 CH100
  kia       /api/bin/dealer  + slapwl(CH)  DE.. FR.. ES242 NL.. BE.. CH101

Blocked / deferred (documented, NOT loaded here — no invented data):
  mercedes, ford                → Akamai WAF hard-block from this host
  peugeot/citroen/opel          → Stellantis PSA backend DNS dead (502)
  renault/dacia, seat, fiat     → VERIFIED but need geo-sweep (lat/lng grid) or
                                  XML parsing; next wave (see DISCOVERY_SCALE_REPORT)

Writes identity/domain candidates to `discovery_candidates`. Dedup is the table's
own partial unique indexes: (domain,country) for domain-ful rows, (source,
registry_id,country) otherwise — so a dealer found by two OEMs/OSM dedups by domain.

Usage:
    python -m scrapers.discovery.sources.oem_locators
    OEM_BRANDS=vw,audi OEM_COUNTRIES=DE,FR python -m scrapers.discovery.sources.oem_locators
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import urllib.parse
from typing import Any, Awaitable, Callable

import asyncpg
import httpx

log = logging.getLogger("oem_locators")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [oem] %(message)s",
)

_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
_COUNTRIES: tuple[str, ...] = ("DE", "FR", "ES", "NL", "BE", "CH")
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_THROTTLE_S = float(os.environ.get("OEM_THROTTLE_S", "0.5"))

# Country geographic centres (lat, lng) for radius-based locators.
_CENTER: dict[str, tuple[float, float]] = {
    "DE": (51.0, 10.0), "FR": (46.6, 2.4), "ES": (40.2, -3.7),
    "NL": (52.2, 5.3), "BE": (50.6, 4.6), "CH": (46.8, 8.2),
}


# ── pure value helpers ─────────────────────────────────────────────────────────
def _f(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _normalize_url(url: Any) -> str | None:
    if not url:
        return None
    url = str(url).strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


def _s(val: Any) -> str | None:
    """Trimmed string or None."""
    if val is None:
        return None
    out = str(val).strip()
    return out or None


# ── pure parsers (one per locator shape) ────────────────────────────────────────
def parse_vw_dealer(d: dict, country: str, source: str) -> dict | None:
    """VW Group SDS dealer (shared by VW + Audi). geoPosition.coordinates is [lng, lat]."""
    name = _s(d.get("name"))
    if not name:
        return None
    addr = d.get("address") or {}
    contact = d.get("contact") or {}
    geo = (d.get("geoPosition") or {}).get("coordinates") or []
    website = _normalize_url(contact.get("website"))
    return {
        "domain": _domain(website), "country": country, "source_layer": 1, "source": source,
        "url": website, "name": name, "address": _s(addr.get("street")),
        "city": _s(addr.get("city")), "postcode": _s(addr.get("postalCode")),
        "phone": _s(contact.get("phoneNumber")), "email": _s(contact.get("email")),
        "lat": _f(geo[1]) if len(geo) > 1 else None,
        "lng": _f(geo[0]) if len(geo) > 0 else None,
        "registry_id": _s(d.get("id")),
        "external_refs": {"sds_partner_id": (d.get("partner") or {}).get("partnerId")},
    }


def parse_skoda_item(it: dict, country: str) -> dict | None:
    """Škoda retailers GetDealers Item. Address carries Latitude/Longitude."""
    name = _s(it.get("Name"))
    if not name:
        return None
    addr = it.get("Address") or {}
    return {
        "domain": None, "country": country, "source_layer": 1, "source": "oem:skoda",
        "url": None, "name": name, "address": _s(addr.get("Street")),
        "city": _s(addr.get("City")), "postcode": _s(addr.get("ZIP")),
        "phone": None, "email": None,
        "lat": _f(addr.get("Latitude")), "lng": _f(addr.get("Longitude")),
        "registry_id": _s(it.get("MarkerId") or it.get("GlobalId") or it.get("Id")),
        "external_refs": {"global_id": it.get("GlobalId")},
    }


def parse_toyota_line(line: str, country: str) -> dict | None:
    """Toyota dealersAutoSuggestion entry: 'UUID=name=city=postcode' (name may hold '=')."""
    parts = (line or "").split("=")
    if len(parts) < 4:
        return None
    uuid, postcode, city = parts[0], parts[-1], parts[-2]
    name = "=".join(parts[1:-2])
    name = _s(name)
    if not name or not _s(uuid):
        return None
    return {
        "domain": None, "country": country, "source_layer": 1, "source": "oem:toyota",
        "url": None, "name": name, "address": None, "city": _s(city),
        "postcode": _s(postcode), "phone": None, "email": None, "lat": None, "lng": None,
        "registry_id": _s(uuid), "external_refs": {"toyota_uuid": _s(uuid)},
    }


def parse_hyundai_dealer(d: dict, country: str) -> dict | None:
    """Hyundai SSR data-js-content dealer (DE/ES/NL/BE/CH). webSite or website[0].url."""
    name = _s(d.get("fullDealerName"))
    if not name:
        return None
    website = d.get("webSite")
    if not website:
        wl = d.get("website")
        if isinstance(wl, list) and wl and isinstance(wl[0], dict):
            website = wl[0].get("url") or wl[0].get("title")
    website = _normalize_url(website)
    cc, phone = _s(d.get("phoneCountryCode")), _s(d.get("phone"))
    phone_full = f"+{cc} {phone}" if cc and phone else phone
    return {
        "domain": _domain(website), "country": country, "source_layer": 1, "source": "oem:hyundai",
        "url": website, "name": name, "address": _s(d.get("addressLine1")),
        "city": _s(d.get("city")), "postcode": _s(d.get("postalCode")),
        "phone": phone_full, "email": _s(d.get("email")),
        "lat": _f(d.get("lat")), "lng": _f(d.get("lng")),
        "registry_id": _s(d.get("id") or d.get("dealerId")),
        "external_refs": {"local_id": d.get("localId")},
    }


def parse_hyundai_uberall(loc: dict, country: str) -> dict | None:
    """Hyundai FR via Uberall storefinder location (no website field)."""
    name = _s(loc.get("name"))
    if not name:
        return None
    return {
        "domain": None, "country": country, "source_layer": 1, "source": "oem:hyundai",
        "url": None, "name": name, "address": _s(loc.get("streetAndNumber")),
        "city": _s(loc.get("city")), "postcode": _s(loc.get("zip")),
        "phone": _s(loc.get("phone")), "email": None,
        "lat": _f(loc.get("lat")), "lng": _f(loc.get("lng")),
        "registry_id": _s(loc.get("identifier")) or _s(loc.get("id")),
        "external_refs": {"uberall_id": loc.get("id")},
    }


def parse_kia_aem(d: dict, country: str) -> dict | None:
    """Kia /api/bin/dealer entry (DE/FR/ES/NL/BE)."""
    name = _s(d.get("dealerName"))
    if not name:
        return None
    return {
        "domain": None, "country": country, "source_layer": 1, "source": "oem:kia",
        "url": None, "name": name, "address": _s(d.get("dealerAddress")),
        "city": _s(d.get("dealerResidence")), "postcode": _s(d.get("dealerPostcode")),
        "phone": _s(d.get("dealerPhone1")), "email": _s(d.get("dealerEmail")),
        "lat": _f(d.get("lat")), "lng": _f(d.get("lng")),
        "registry_id": _s(d.get("dealerExternalid")),
        "external_refs": {"kia_id": _s(d.get("dealerExternalid"))},
    }


def parse_kia_ch(d: dict, country: str = "CH") -> dict | None:
    """Kia CH via dealcore.slapwl.ch dealer-list (filter to brands selling Kia)."""
    name = _s(d.get("name"))
    if not name:
        return None
    brands = d.get("brands") or []
    if brands and not any(
        (b.get("name") == "Kia" and b.get("sell")) for b in brands if isinstance(b, dict)
    ):
        return None
    return {
        "domain": None, "country": "CH", "source_layer": 1, "source": "oem:kia",
        "url": None, "name": name, "address": _s(d.get("street")),
        "city": _s(d.get("city")), "postcode": _s(d.get("zip")),
        "phone": _s(d.get("phone")), "email": _s(d.get("email")),
        "lat": _f(d.get("latitude")), "lng": _f(d.get("longitude")),
        "registry_id": _s(d.get("id")),
        "external_refs": {"kia_slug": d.get("slug")},
    }


# ── brand fetchers (network) ─────────────────────────────────────────────────────
_SDS_URL = "https://oneapi.volkswagen.com/go-sds/search/v2/dealers"
_SDS_KEY = "jBQFyVGCKv71Knmignx4bKDYnTH0gfve"  # public key embedded in VW SPA config
_VW_TENANTS = {"DE": ("v-deu-dcc", "de_DE"), "FR": ("v-fra-dcc", "fr_FR"),
               "ES": ("v-esp-dcc", "es_ES"), "NL": ("v-nld-dcc", "nl_NL"),
               "CH": ("v-che-dcc", "de_CH")}  # BE → 204 (not registered in SDS)
_AUDI_TENANTS = {"DE": ("a-deu-dcc", "de_DE"), "FR": ("a-fra-dcc", "fr_FR"),
                 "ES": ("a-esp-dcc", "es_ES"), "NL": ("a-nld-dcc", "nl_NL"),
                 "BE": ("a-bel-dcc", "fr_BE"), "CH": ("a-che-dcc", "de_CH")}


async def _fetch_sds(client, country, tenants, source) -> list[dict]:
    cfg = tenants.get(country)
    if not cfg:
        return []
    tenant, language = cfg
    r = await client.get(_SDS_URL, params={
        "tenant": tenant, "country": country, "language": language, "limit": 10000,
    }, headers={"x-api-key": _SDS_KEY, "Accept": "application/json"})
    if r.status_code != 200:
        log.warning("%s %s HTTP %d", source, country, r.status_code)
        return []
    dealers = r.json().get("dealers") or []
    return [c for c in (parse_vw_dealer(d, country, source) for d in dealers) if c]


async def fetch_vw(client, country):
    return await _fetch_sds(client, country, _VW_TENANTS, "oem:vw")


async def fetch_audi(client, country):
    return await _fetch_sds(client, country, _AUDI_TENANTS, "oem:audi")


_SKODA = {  # (host, bid, culture)
    "DE": ("www.skoda-auto.de", "107", "de-DE"), "FR": ("www.skoda.fr", "995", "fr-FR"),
    "ES": ("www.skoda.es", "572", "es-ES"), "NL": ("www.skoda.nl", "438", "nl-NL"),
    "BE": ("nl.skoda.be", "202", "nl-BE"), "CH": ("www.skoda.ch", "223", "de-CH"),
}


async def fetch_skoda(client, country):
    cfg = _SKODA.get(country)
    if not cfg:
        return []
    host, bid, culture = cfg
    lat, lng = _CENTER[country]
    url = f"https://{host}/apps/retailers/api/{bid}/{culture}/Dealers/GetDealers"
    r = await client.get(url, params={"lat": lat, "lng": lng, "distance": 2000},
                         headers={"Accept": "application/json",
                                  "Referer": f"https://{host}/apps/retailers",
                                  "User-Agent": _BROWSER_UA})
    if r.status_code != 200:
        log.warning("oem:skoda %s HTTP %d", country, r.status_code)
        return []
    items = r.json().get("Items") or []
    return [c for c in (parse_skoda_item(it, country) for it in items) if c]


_TOYOTA = {  # (host, lang, referer-path)
    "DE": ("www.toyota.de", "de", "haendlersuche"), "FR": ("www.toyota.fr", "fr", "concessionnaires"),
    "ES": ("www.toyota.es", "es", "concesionarios"), "NL": ("www.toyota.nl", "nl", "dealer-zoeken"),
    "BE": ("nl.toyota.be", "nl", "nl/dealer-zoeken"), "CH": ("de.toyota.ch", "de", "de/haendlersuche"),
}


async def fetch_toyota(client, country):
    cfg = _TOYOTA.get(country)
    if not cfg:
        return []
    host, lang, refpath = cfg
    url = f"https://{host}/var/dxp/forms/datasources/dealersAutoSuggestion"
    r = await client.get(url, params={"q": "", "country": country, "language": lang, "brand": "TOYOTA"},
                         headers={"Accept": "application/json", "User-Agent": _BROWSER_UA,
                                  "Referer": f"https://{host}/{refpath}"})
    if r.status_code != 200:
        log.warning("oem:toyota %s HTTP %d", country, r.status_code)
        return []
    lines = r.json()
    if not isinstance(lines, list):
        return []
    return [c for c in (parse_toyota_line(ln, country) for ln in lines) if c]


_HYUNDAI_SSR = {
    "DE": ("https://www.hyundai.com/de/de/beratung-kauf/entdecken-und-erwerben/haendlersuche.html", "de"),
    "ES": ("https://www.hyundai.com/es/es/concesionarios.html", "es"),
    "NL": ("https://www.hyundai.com/nl/nl/dealers.html", "nl"),
    "BE": ("https://www.hyundai.com/be/nl/dealers.html", "be"),
    "CH": ("https://www.hyundai.com/ch/de/vertriebsnetz-schweiz.html", "ch"),
}
_HYUNDAI_FR_UBERALL = (
    "https://uberall.com/api/storefinders/gSNTstbODTSmkLJopDa5r6buAP1PHN/locations/all?max=1000&offset=0"
)
_DATA_JS_RE = re.compile(r"data-js-content='([^']+)'")


async def fetch_hyundai(client, country):
    if country == "FR":
        r = await client.get(_HYUNDAI_FR_UBERALL, headers={"Accept": "application/json", "User-Agent": _BROWSER_UA})
        if r.status_code != 200:
            log.warning("oem:hyundai FR HTTP %d", r.status_code)
            return []
        locs = (r.json().get("response") or {}).get("locations") or []
        return [c for c in (parse_hyundai_uberall(loc, "FR") for loc in locs) if c]
    cfg = _HYUNDAI_SSR.get(country)
    if not cfg:
        return []
    url, key = cfg
    r = await client.get(url, headers={"User-Agent": _BROWSER_UA})
    if r.status_code != 200:
        log.warning("oem:hyundai %s HTTP %d", country, r.status_code)
        return []
    m = _DATA_JS_RE.search(r.text)
    if not m:
        log.warning("oem:hyundai %s — no data-js-content block", country)
        return []
    try:
        payload = json.loads(m.group(1).replace("&quot;", '"').replace("&#39;", "'"))
    except json.JSONDecodeError:
        try:
            payload = json.loads(m.group(1))
        except json.JSONDecodeError:
            log.warning("oem:hyundai %s — data-js-content not JSON", country)
            return []
    dealers = (payload.get("dealers") or {}).get(key) or []
    return [c for c in (parse_hyundai_dealer(d, country) for d in dealers) if c]


# Kia AEM /api/bin/dealer: the lat/lng path is capped to a handful of nearest
# dealers (DE→92, FR→26 at any radius), but a broad keyword returns the whole
# national set (verified 2026-06-07: DE≈400, FR=228, ES=242, NL=77). BE is not
# served by this endpoint (nl-be and fr-be both return 0) → omitted, not faked.
_KIA_AEM = {"DE": "de-de", "FR": "fr-fr", "ES": "es-es", "NL": "nl-nl"}
_KIA_KEYWORD = os.environ.get("KIA_KEYWORD", "a")
_KIA_CH_URL = "https://dealcore.slapwl.ch/de/kia/ch/corporate/dealer-list?filter=all"


async def fetch_kia(client, country):
    if country == "CH":
        r = await client.get(_KIA_CH_URL, headers={"Accept": "application/json", "User-Agent": _BROWSER_UA,
                                                   "Origin": "https://www.kia.ch",
                                                   "Referer": "https://www.kia.ch/haendlersuche"})
        if r.status_code != 200:
            log.warning("oem:kia CH HTTP %d", r.status_code)
            return []
        data = r.json()
        rows = data if isinstance(data, list) else (data.get("list") or [])
        return [c for c in (parse_kia_ch(d) for d in rows) if c]
    locale = _KIA_AEM.get(country)
    if not locale:
        return []  # BE not served by Kia's /api/bin/dealer endpoint
    r = await client.get("https://www.kia.com/api/bin/dealer",
                         params={"program": "find", "locale": locale, "keyword": _KIA_KEYWORD},
                         headers={"Accept": "application/json", "User-Agent": _BROWSER_UA})
    if r.status_code != 200:
        log.warning("oem:kia %s HTTP %d", country, r.status_code)
        return []
    rows = r.json().get("list") or []
    return [c for c in (parse_kia_aem(d, country) for d in rows) if c]


# brand → (fetcher, countries it serves)
BRANDS: dict[str, tuple[Callable[[Any, str], Awaitable[list[dict]]], tuple[str, ...]]] = {
    "vw":      (fetch_vw,      tuple(_VW_TENANTS)),
    "audi":    (fetch_audi,    tuple(_AUDI_TENANTS)),
    "skoda":   (fetch_skoda,   tuple(_SKODA)),
    "toyota":  (fetch_toyota,  tuple(_TOYOTA)),
    "hyundai": (fetch_hyundai, ("DE", "FR", "ES", "NL", "BE", "CH")),
    "kia":     (fetch_kia,     ("DE", "FR", "ES", "NL", "CH")),  # BE unsupported by Kia API
}


# ── sink (mirrors orchestrator: domain path | identity path) ─────────────────────
_COLS = ("domain, country, source_layer, source, url, name, address, city, postcode, "
         "phone, email, lat, lng, registry_id, external_refs")
_VALS = "$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb"
_UPSERT_DOMAIN = f"""
INSERT INTO discovery_candidates ({_COLS}) VALUES ({_VALS})
ON CONFLICT (domain, country) WHERE domain IS NOT NULL
DO UPDATE SET last_seen = NOW() WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""
_UPSERT_IDENTITY = f"""
INSERT INTO discovery_candidates ({_COLS}) VALUES ({_VALS})
ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
DO UPDATE SET last_seen = NOW() WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""


async def _upsert(pool: asyncpg.Pool, c: dict) -> bool:
    domain, registry_id = c.get("domain"), c.get("registry_id")
    if not domain and not registry_id:
        return False
    params = (domain, c.get("country"), c.get("source_layer"), c.get("source"), c.get("url"),
              c.get("name"), c.get("address"), c.get("city"), c.get("postcode"), c.get("phone"),
              c.get("email"), c.get("lat"), c.get("lng"), registry_id,
              json.dumps(c.get("external_refs") or {}))
    try:
        await pool.execute(_UPSERT_DOMAIN if domain else _UPSERT_IDENTITY, *params)
        return True
    except Exception as exc:  # noqa: BLE001 — one bad row must not abort the sweep
        log.warning("upsert failed source=%s name=%r: %s", c.get("source"), (c.get("name") or "")[:50], exc)
        return False


async def run(brands: list[str] | None = None, countries: list[str] | None = None) -> dict[str, int]:
    brands = brands or [b.strip() for b in os.environ.get("OEM_BRANDS", "").split(",") if b.strip()] or list(BRANDS)
    countries = countries or [c.strip().upper() for c in os.environ.get("OEM_COUNTRIES", "").split(",") if c.strip()] or list(_COUNTRIES)
    stats: dict[str, int] = {}
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=6)
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            for brand in brands:
                entry = BRANDS.get(brand)
                if not entry:
                    log.warning("unknown brand %s — skipping", brand)
                    continue
                fetch, brand_countries = entry
                for country in countries:
                    if country not in brand_countries:
                        continue
                    try:
                        cands = await fetch(client, country)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("oem:%s %s fetch errored: %s", brand, country, exc)
                        cands = []
                    written = 0
                    for cand in cands:
                        if await _upsert(pool, cand):
                            written += 1
                    stats[f"{country}:oem:{brand}"] = written
                    log.info("oem:%s %s — %d fetched / %d written", brand, country, len(cands), written)
                    await asyncio.sleep(_THROTTLE_S)
    finally:
        await pool.close()
    total = sum(stats.values())
    log.info("DONE oem_locators — %d candidates written across %d (brand,country)", total, len(stats))
    return stats


if __name__ == "__main__":
    asyncio.run(run())
