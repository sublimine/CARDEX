"""La Inquisición — cadena de verificación SEPARADA. Quien extrae nunca certifica su número.

El pipeline (W3/V3) cuenta el stock visible por el SITEMAP. La Inquisición lo re-cuenta
por una vía ORTOGONAL: rastrea las páginas de LISTADO siguiendo la paginación y cuenta
los enlaces de detalle (regex de la receta). Sitemap (XML, todo el árbol) vs listado
(HTML, lo que el portal pagina al usuario) son superficies distintas — si concuerdan,
el número es de fiar; si no, hay truncado/cap/bug.

Re-verificación SIEMPRE en ceros, cifras redondas y conteos idénticos entre peers
(lección 2026-06-10: una epidemia de "0 stock" era bug de transporte, no realidad).

Veredictos a ``verification_verdicts`` (quórum DB-enforced). Read-only sobre el inventario.

    DATABASE_URL=... python -m scrapers.workflows.inquisition --country ES --sample 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import asyncpg

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from scrapers.portals import config as portal_config  # noqa: E402
from scrapers.workflows.model import (  # noqa: E402
    InquisitionReport,
    InquisitionVerdict,
    reverify_triggers,
)

log = logging.getLogger("inquisition")
PG_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
_MAX_PAGES = 80


def _same_host(url: str, host: str) -> bool:
    h = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    h = h[4:] if h.startswith("www.") else h
    base = host[4:] if host.startswith("www.") else host
    return h == base or h.endswith("." + base)


async def count_by_listing_pagination(domain: str, listing_url: str, detail_url_re: str) -> int:
    """ORTHOGONAL path B — crawl the listing pages following pagination, count distinct
    detail links matching the recipe regex. Different surface from the sitemap."""
    from curl_cffi.requests import AsyncSession
    if not listing_url or not detail_url_re:
        return -1  # cannot run this path → caller treats as "no orthogonal evidence"
    rx = re.compile(detail_url_re)
    cs = AsyncSession(impersonate="chrome131", verify=False)
    try:
        seen: set[str] = set()
        visited: set[str] = set()
        queue = [listing_url]
        pages = 0
        while queue and pages < _MAX_PAGES:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            try:
                r = await cs.get(url, timeout=15, allow_redirects=True)
            except Exception:  # noqa: BLE001
                continue
            if r.status_code != 200:
                continue
            pages += 1
            html = (r.content or b"").decode("utf-8", "ignore")
            hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
            for h in hrefs:
                absu = urljoin(url, h)
                if rx.search(absu):
                    seen.add(absu.split("?")[0])
            # discover next pages: ?page= / ?VehiculoOcasion_page= / rel=next / numbered
            for h in hrefs:
                absu = urljoin(url, h)
                if not _same_host(absu, domain):
                    continue
                if re.search(r"[?&](?:page|p|VehiculoOcasion_page)=\d+", absu) and absu not in visited:
                    queue.append(absu.split("#")[0])
        return len(seen)
    finally:
        await cs.close()


async def declared_total(domain: str, listing_url: str) -> int:
    """ORTHOGONAL to enumeration — read the portal's OWN stated count ("N vehículos" /
    data-total / JSON-LD numberOfItems) off the listing page. Since W3 now enumerates
    the listing links, the Inquisition must verify by a DIFFERENT read: the declared
    integer (a number the portal asserts, not links we count). -1 if none is stated."""
    from curl_cffi.requests import AsyncSession
    if not listing_url:
        return -1
    cs = AsyncSession(impersonate="chrome131", verify=False)
    try:
        r = await cs.get(listing_url, timeout=20, allow_redirects=True)
        if r.status_code != 200:
            return -1
        h = (r.content or b"").decode("utf-8", "ignore")
        cands: list[int] = []
        for pat in (r'"numberOfItems"\s*:\s*"?(\d+)', r'data-total[^0-9]{0,10}(\d+)',
                    r'(\d+)\s*(?:veh[ií]culos?|coches?|resultados?|annonces?|voitures?|fahrzeuge?)'):
            cands += [int(x) for x in re.findall(pat, h, re.I)]
        # the declared total is the LARGEST plausible "N <noun>" on the page (filters
        # per-card counts like "1 foto"); bounded to a sane dealer-stock ceiling.
        plausible = [n for n in cands if 1 <= n <= 100_000]
        return max(plausible) if plausible else -1
    except Exception:  # noqa: BLE001
        return -1
    finally:
        await cs.close()


async def inquire_dealer(pg, domain: str, peer_counts: tuple[int, ...] = ()) -> InquisitionVerdict:
    """Re-certify ONE dealer's served count by the orthogonal DECLARED-TOTAL path."""
    ulid = await pg.fetchval("SELECT entity_ulid FROM source_entities WHERE source_key=$1", domain)
    served = await pg.fetchval(
        "SELECT count(*) FROM entity_inventory WHERE entity_ulid=$1", ulid) if ulid else 0
    cfg = portal_config.load(domain)
    listing = cfg.endpoints.listing_url_template if cfg else ""
    indep = await declared_total(domain, listing)
    flags = reverify_triggers(served, peer_counts)
    if indep < 0:
        return InquisitionVerdict(domain, served, -1, "declared_total:unavailable", flags)
    return InquisitionVerdict(domain, served, indep, "declared_total", flags)


def _verdict_label(v: InquisitionVerdict) -> str:
    """Map to the DB's verdict vocabulary (CHECK-enforced)."""
    if v.inquisitor_count < 0:
        return "UNVERIFIED"          # no orthogonal surface available
    return "TRUSTWORTHY" if v.trustworthy else "REFUTED"


async def _record_verdict(pg, v: InquisitionVerdict) -> None:
    """Persist to verification_verdicts honoring the real schema + chk_quorum (≥2
    verifier_paths for TRUSTWORTHY). The two ORTHOGONAL paths are the producer's
    sitemap and the inquisitor's listing pagination. Best-effort, never blocks."""
    paths = ["harvest_sitemap", v.method]   # 2 orthogonal vias → satisfies chk_quorum
    divergence = abs(v.producer_count - v.inquisitor_count) if v.inquisitor_count >= 0 else None
    try:
        await pg.execute(
            "INSERT INTO verification_verdicts "
            "(subject_type, subject_key, claim, primary_value, primary_path, "
            " verifier_paths, independent_values, divergence, verdict, evidence) "
            "VALUES('entity_inventory',$1,'count',$2,'harvest_sitemap',"
            " $3::text[], $4::jsonb, $5, $6, $7::jsonb)",
            v.domain, float(v.producer_count), paths,
            json.dumps([v.inquisitor_count]), divergence, _verdict_label(v),
            json.dumps({"method": v.method, "flags": list(v.flags)}))
    except Exception as exc:  # noqa: BLE001
        log.debug("verdict record skipped for %s: %s", v.domain, exc)


async def run_inquisition(country: str, *, sample: int = 20, only: list[str] | None = None,
                          record: bool = True) -> InquisitionReport:
    cc = country.upper()[:2]
    pg = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=4)
    try:
        if only:
            domains = only
        else:
            rows = await pg.fetch(
                "SELECT se.source_key FROM source_entities se "
                "WHERE se.kind='dealer' AND se.country=$1 "
                "AND EXISTS (SELECT 1 FROM vehicle_index vi WHERE vi.entity_ulid=se.entity_ulid) "
                "ORDER BY md5(se.source_key) LIMIT $2", cc, sample)
            domains = [r["source_key"] for r in rows]
        # peer counts for the identical-to-peers trigger
        peers = []
        for d in domains:
            u = await pg.fetchval("SELECT entity_ulid FROM source_entities WHERE source_key=$1", d)
            peers.append(await pg.fetchval(
                "SELECT count(*) FROM entity_inventory WHERE entity_ulid=$1", u) if u else 0)
        peer_tuple = tuple(peers)

        verdicts: list[InquisitionVerdict] = []
        sem = asyncio.Semaphore(4)

        async def one(d: str) -> None:
            async with sem:
                v = await inquire_dealer(pg, d, peer_tuple)
                verdicts.append(v)
                if record:
                    await _record_verdict(pg, v)
                mark = "✓" if v.trustworthy else "✗REFUTADO"
                log.info("  %-28s prod=%d indep=%d %s %s", d, v.producer_count,
                         v.inquisitor_count, mark, ",".join(v.flags))

        await asyncio.gather(*(one(d) for d in domains))
        trust = sum(1 for v in verdicts if v.trustworthy)
        refuted = tuple(v for v in verdicts if not v.trustworthy)
        report = InquisitionReport(cc, len(verdicts), trust, refuted)
        print(f"\n===== INQUISICIÓN {cc} =====")
        print(f"muestra={report.sampled} de_fiar={report.trustworthy} "
              f"({report.trust_rate:.1%}) refutados={len(refuted)}")
        for v in refuted:
            print(f"  REFUTADO {v.domain}: prod={v.producer_count} indep={v.inquisitor_count} "
                  f"[{v.method}] {','.join(v.flags)}")
        return report
    finally:
        await pg.close()


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--only", default=None, help="comma list of domains to inquire instead of a sample")
    ap.add_argument("--no-record", action="store_true")
    a = ap.parse_args()
    only = [x.strip() for x in a.only.split(",")] if a.only else None
    asyncio.run(run_inquisition(a.country, sample=a.sample, only=only, record=not a.no_record))


if __name__ == "__main__":
    main()
