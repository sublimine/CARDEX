"""
CH discovery — AGVS/UPSA member directory (the Swiss garage federation).

AGVS (Auto Gewerbe Verband Schweiz / UPSA) publishes its full member list on a
single public page, embedded as HTML-encoded JSON objects. Every member is a
vetted Swiss car garage/dealer, and ~88% carry the member's OWN website — making
this the highest-signal CH source for dealers WITH a domain (the bridge to
inventory extraction). One GET, no anti-bot, no pagination.

    https://www.agvs-upsa.ch/de/verband/mitglieder/mitgliederverzeichnis/

Verified live 2026-06-07: 3,661 members, 3,223 with a populated ``url``.

Each object is flat: {surname,street,zip,city,phone,email,url,latitude,longitude}.
There is no stable registry id in the payload, so we synthesise a deterministic
one (sha1 of name|zip|city) to give domain-less members an identity-dedup key.
Domain-ful members dedup cross-source by (domain,country) — collapsing against
OSM/OEM rows for the same dealer.

Usage:
    python -m scrapers.discovery.sources.ch_agvs
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import os
import re
import urllib.parse

import asyncpg
import httpx

log = logging.getLogger("ch_agvs")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [ch_agvs] %(message)s",
)

_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
_URL = "https://www.agvs-upsa.ch/de/verband/mitglieder/mitgliederverzeichnis/"
_SOURCE = "agvs"
_SOURCE_LAYER = 2
_COUNTRY = "CH"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
_MEMBER_RE = re.compile(r'\{"surname":[^{}]*\}')


def _s(v) -> str | None:
    if v is None:
        return None
    out = str(v).strip()
    return out or None


def _f(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _normalize_url(u) -> str | None:
    if not u:
        return None
    u = str(u).strip()
    if not u:
        return None
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u.rstrip("/")


def _domain(u: str | None) -> str | None:
    if not u:
        return None
    try:
        netloc = urllib.parse.urlparse(u).netloc.lower()
    except ValueError:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


def _synth_id(name: str | None, zip_: str | None, city: str | None) -> str | None:
    key = "|".join(x or "" for x in (name, zip_, city)).strip("|")
    if not key:
        return None
    return "agvs-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def to_candidate(obj: dict) -> dict:
    """Map one AGVS member object to a discovery candidate (pure)."""
    name = _s(obj.get("surname"))
    website = _normalize_url(obj.get("url"))
    zip_ = _s(obj.get("zip"))
    city = _s(obj.get("city"))
    return {
        "domain": _domain(website),
        "country": _COUNTRY,
        "source_layer": _SOURCE_LAYER,
        "source": _SOURCE,
        "url": website,
        "name": name,
        "address": _s(obj.get("street")),
        "city": city,
        "postcode": zip_,
        "phone": _s(obj.get("phone")),
        "email": _s(obj.get("email")),
        "lat": _f(obj.get("latitude")),
        "lng": _f(obj.get("longitude")),
        "registry_id": _synth_id(name, zip_, city),
        "external_refs": {"federation": "AGVS/UPSA"},
    }


def parse_members(raw_html: str) -> list[dict]:
    """Extract member candidate dicts from the page HTML (pure)."""
    text = html.unescape(raw_html)
    out: list[dict] = []
    for block in _MEMBER_RE.findall(text):
        try:
            obj = json.loads(block)
        except json.JSONDecodeError:
            continue
        cand = to_candidate(obj)
        if cand["name"]:
            out.append(cand)
    return out


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
    params = (domain, c["country"], c["source_layer"], c["source"], c.get("url"), c.get("name"),
              c.get("address"), c.get("city"), c.get("postcode"), c.get("phone"), c.get("email"),
              c.get("lat"), c.get("lng"), registry_id, json.dumps(c.get("external_refs") or {}))
    try:
        await pool.execute(_UPSERT_DOMAIN if domain else _UPSERT_IDENTITY, *params)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("upsert failed name=%r: %s", (c.get("name") or "")[:50], exc)
        return False


async def run() -> int:
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        r = await client.get(_URL, headers={"User-Agent": _UA})
    if r.status_code != 200:
        log.warning("AGVS HTTP %d — abort", r.status_code)
        return 0
    candidates = parse_members(r.text)
    with_web = sum(1 for c in candidates if c["domain"])
    log.info("AGVS parsed=%d with_web=%d", len(candidates), with_web)
    written = 0
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    try:
        for c in candidates:
            if await _upsert(pool, c):
                written += 1
    finally:
        await pool.close()
    log.info("DONE ch_agvs parsed=%d with_web=%d upserted=%d", len(candidates), with_web, written)
    return written


if __name__ == "__main__":
    asyncio.run(run())
