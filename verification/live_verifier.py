"""Live entity verification — Layer 2 of the verification team (the half code cannot fake).

``verifier.py`` (Layer 1) proves every PG-side dimension deterministically: identity, servability,
linkage, fields, dedup, delta, staleness, count_coverage. It proves the database is self-consistent.
It can NOT prove the persisted data still matches the SOURCE today — a connector can rot, a source
can re-skin, a price can flip from cash to lease, a listing can sell — and Layer 1 would still pass
because the DB still agrees with itself. This module closes that gap by re-fetching the live source
TODAY and diffing field-by-field against what we persisted, by the source's own truth.

It produces ``DimResult``s of the SAME shape as ``verifier.py`` (imported, not redefined) so a future
``verify_entity_team`` orchestrator concatenates both dim lists into ONE verdict. The severity ladder,
PASS/GAP/FAIL/NEEDS_LIVE vocabulary, and ``Verdict`` interface (``.verified`` / ``.gaps`` / ``.add``)
are reused verbatim — Layer 2 dims drop straight into ``gap_router.route`` alongside Layer 1's.

Live dimensions (all adversarial — each tries to FAIL the entity; uncertainty is a GAP, never PASS):
  1. ACCESS              re-fetch the source listing today; 200 + parseable, no ban/empty regression.
  2. FIELD_VS_LIVE_DETAIL  random sample of served rows, fetch EACH detail page fresh, diff
                         price/year/km/title persisted-vs-live; report match-rate. A 404 = listing gone.
  3. PRICE_TRAP_LIVE     on those pages, confirm the served price equals the CASH price the connector
                         designates (its ``price_trap`` doctrine), not the monthly/lease figure.
  4. COUNT_2WAY_LIVE     re-derive the source's declared total two independent ways live (the
                         connector's own ``count_verify``) so Layer 1's count_coverage gets a REAL
                         declared figure instead of NEEDS_LIVE.
  5. QUORUM              structured skeptic fan-out per surviving claim (see ``dim_quorum``).

The LIVE fetch/parse is NOT reimplemented here: each already-committed ``seal_<x>.py`` connector owns
the platform's fetch + rich-field parser, and this module DISPATCHES to it through a thin per-domain
adapter (``_ADAPTERS``). One source of parsing truth; the verifier and the harvester read the live page
the same way, so a diff is a real diff, never a parser-skew artefact.

    python -m verification.live_verifier --domain autocasion.com
    python -m verification.live_verifier --domain autocasion.com --connector scripts/seal_autocasion.py
    python -m verification.live_verifier --domain pkw.de --sample 8 --no-count
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import random
import sys
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import asyncpg
from curl_cffi.requests import AsyncSession

# Reuse Layer 1's shapes verbatim so the two layers compose into one verdict. NO redefinition.
from verification.verifier import (
    DimResult, Verdict, CRITICAL, HIGH, MEDIUM, LOW,
    PASS, GAP, FAIL, NEEDS_LIVE, _sev_rank,
)
from scrapers.dealer_scraping.inventory_harvester import _entity_ulid

# Windows consoles default to cp1252 and choke on accented titles / arrows. UTF-8-safe stdout at
# import time (mirrors verifier.py — single point of repair) so importers print cleanly.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:  # noqa: BLE001
    pass

DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")

IMPERSONATE = "chrome136"          # SESSION-level TLS only; current-Chrome floor per CARDEX doctrine.
SAMPLE_N = 8                       # detail pages fetched fresh for the field diff (small + bounded).
SLEEP = 1.2                        # polite jitter floor between live detail fetches.
_MATCH_PASS = 0.80                 # field-vs-live match-rate at/above which FIELD_VS_LIVE_DETAIL PASSes.
_TRAP_PASS = 0.85                  # cash-price agreement at/above which PRICE_TRAP_LIVE PASSes.
_COUNT_AGREE = 0.90                # 2-way count agreement at/above which COUNT_2WAY_LIVE is clean.
_BAN_TELLS = ("just a moment", "verifying you are human", "access denied",
              "captcha", "cf-chl", "datadome", "px-captcha", "are you a robot")


# ---------------------------------------------------------------- connector adapter (dispatch only)
@dataclass
class ConnectorAdapter:
    """Thin bridge to an already-committed ``seal_<x>.py`` connector. It does NO parsing of its own —
    it routes the live fetch + field extraction into the connector's own functions, so the verifier
    and the harvester read the live page identically (a diff is a real diff, not parser skew).

    Fields:
      module          the imported connector module.
      access_url      the source listing/SRP/API URL to re-fetch for the ACCESS dimension.
      parse_listing   (resp_text) -> (n_items:int, note:str); how many listings the SRP yielded.
      fetch_detail    async (sess, source_url) -> {'status':int, 'fields':dict|None}; fresh per-detail
                      fetch+parse using the connector's parser. fields keys: price/year/km/title.
      count_verify    async (sess) -> (declared:int|None, way2:int|None); connector's own 2-way count.
      price_trap_doc  the connector's documented CASH-price node (provenance for PRICE_TRAP_LIVE).
    """
    module: Any
    access_url: str
    parse_listing: Callable[[str], tuple[int, str]]
    fetch_detail: Callable[[AsyncSession, str], Awaitable[dict]]
    count_verify: Callable[[AsyncSession], Awaitable[tuple[int | None, int | None]]]
    price_trap_doc: str


def _adapter_autocasion() -> ConnectorAdapter:
    m = importlib.import_module("scripts.seal_autocasion")

    def parse_listing(text: str) -> tuple[int, str]:
        anchors = set(m.DET.findall(text or ""))
        return len(anchors), f"{len(anchors)} detail anchors on SRP"

    async def fetch_detail(sess: AsyncSession, url: str) -> dict:
        r = await m._get(sess, url)
        if r.status_code != 200 or not r.text:
            return {"status": r.status_code, "fields": None}
        return {"status": 200, "fields": m.parse_detail(r.text, url)}

    return ConnectorAdapter(
        module=m, access_url=m.GLOBAL_SRP, parse_listing=parse_listing,
        fetch_detail=fetch_detail, count_verify=m.count_verify,
        price_trap_doc="detail ld+json @type=Product offers.price = CASH EUR "
                       "(== GTM price == share-text == meta-desc; financing widget exposes no /mes).")


def _adapter_largus() -> ConnectorAdapter:
    m = importlib.import_module("scripts.seal_largus")

    def parse_listing(text: str) -> tuple[int, str]:
        links = m._deeplinks(text)
        return len(links), f"{len(links)} annonce deep-links on /auto/"

    async def fetch_detail(sess: AsyncSession, url: str) -> dict:
        r = await m._get(sess, url)
        if r.status_code != 200 or not r.text:
            return {"status": r.status_code, "fields": None}
        # enrich() wraps the same ld+json parser; call the parser directly to keep the status code.
        from scripts import platform_seal as ps
        return {"status": 200, "fields": ps.parse_ldjson_vehicle(r.text, url)}

    return ConnectorAdapter(
        module=m, access_url=f"{m.BASE}/auto/", parse_listing=parse_listing,
        fetch_detail=fetch_detail, count_verify=m.count_verify,
        price_trap_doc="ld+json offers.price = CASH (EUR); no /mois·mensualité·comptant field "
                       "competes in structured data.")


def _adapter_pkw() -> ConnectorAdapter:
    """pkw.de has no per-detail page — the search JSON carries the rich fields. The live field diff
    re-derives a row from the search API keyed by its url (the connector's ``parse_results``)."""
    m = importlib.import_module("scripts.seal_pkw")

    def parse_listing(text: str) -> tuple[int, str]:
        # ACCESS for a JSON API: a parseable page == a results array. _get_json already gates 200.
        import json
        try:
            payload = json.loads(text or "{}")
        except (ValueError, TypeError):
            return 0, "search endpoint did not return JSON"
        rows = m.parse_results(payload)
        return len(rows), f"{len(rows)} results in search page"

    async def fetch_detail(sess: AsyncSession, url: str) -> dict:
        # No detail page: walk the search pages until the url appears, parse that row. Bounded.
        for page in range(1, 12):
            payload = await m._get_json(sess, f"{m.API}?page={page}")
            for row in m.parse_results(payload):
                if row.get("url") == url:
                    return {"status": 200, "fields": row}
            await asyncio.sleep(0.4)
            if page >= ((payload.get("total") or {}).get("pages") or 1):
                break
        return {"status": 410, "fields": None}        # not in live results -> treat as GONE.

    return ConnectorAdapter(
        module=m, access_url=f"{m.API}?page=1", parse_listing=parse_listing,
        fetch_detail=fetch_detail, count_verify=m.count_verify,
        price_trap_doc="price.customer = gross CASH (EUR); NOT netto_price / initial_price / "
                       "predicted / monthly_cost (financing).")


# Registry keyed by the canonical source domain. Add an entry per proxy-free connector.
_ADAPTERS: dict[str, Callable[[], ConnectorAdapter]] = {
    "autocasion.com": _adapter_autocasion,
    "occasion.largus.fr": _adapter_largus,
    "pkw.de": _adapter_pkw,
}

# Map a --connector path (scripts/seal_x.py) to a domain when the domain is omitted/ambiguous.
_CONNECTOR_DOMAIN = {
    "seal_autocasion": "autocasion.com",
    "seal_largus": "occasion.largus.fr",
    "seal_pkw": "pkw.de",
}


def _resolve_adapter(domain: str | None, connector: str | None) -> tuple[str, ConnectorAdapter]:
    """Pick the connector adapter from --domain, else infer it from the --connector file stem.
    Fails LOUDLY (no silent guess) if neither resolves to a registered proxy-free connector."""
    dom = (domain or "").strip().lower()
    if not dom and connector:
        stem = os.path.splitext(os.path.basename(connector))[0]
        dom = _CONNECTOR_DOMAIN.get(stem, "")
    if dom not in _ADAPTERS:
        known = ", ".join(sorted(_ADAPTERS))
        raise SystemExit(
            f"no registered live adapter for domain={domain!r} connector={connector!r}. "
            f"Registered proxy-free connectors: {known}. "
            f"Add an adapter to verification/live_verifier._ADAPTERS to verify a new source live.")
    return dom, _ADAPTERS[dom]()


# ------------------------------------------------------------------------------- field comparison
def _norm_price(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(round(float(v)))          # DB Decimal('6900.00') and parser int 6900 must compare equal.
    except (ValueError, TypeError):
        return None


def _norm_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _norm_title(v: Any) -> str | None:
    if not v:
        return None
    return " ".join(str(v).lower().split())


def _title_match(persisted: str | None, live: str | None) -> bool:
    """Titles are noisy (the connector concatenates make+model+variant). Count a match when the
    shorter normalized title is a substring of the longer, or they share their leading token."""
    p, l = _norm_title(persisted), _norm_title(live)
    if not p or not l:
        return p == l
    if p in l or l in p:
        return True
    return p.split()[0] == l.split()[0]


def _diff_row(persisted: dict, live: dict) -> dict:
    """Field-by-field persisted-vs-live comparison for ONE listing. Returns per-field
    match booleans (only for fields the live page actually provides — a field the source omits
    is not counted against the match-rate) plus the raw pair for evidence on mismatch."""
    out: dict[str, Any] = {"fields": {}, "mismatch": {}}

    def cmp(name: str, p_val: Any, l_val: Any, equal: Callable[[Any, Any], bool]) -> None:
        if l_val is None:                      # source omits it live -> not a diff signal, skip.
            return
        ok = equal(p_val, l_val)
        out["fields"][name] = ok
        if not ok:
            out["mismatch"][name] = {"persisted": p_val, "live": l_val}

    cmp("price", _norm_price(persisted.get("price")), _norm_price(live.get("price")),
        lambda a, b: a == b)
    cmp("year", _norm_int(persisted.get("year")), _norm_int(live.get("year")),
        lambda a, b: a == b)
    cmp("km", _norm_int(persisted.get("mileage_km")), _norm_int(live.get("km")),
        lambda a, b: a is not None and b is not None and abs(a - b) <= max(1, round(a * 0.02)))
    cmp("title", persisted.get("title"), live.get("title"), _title_match)
    return out


# ------------------------------------------------------------------------------------- dimensions
async def dim_access(sess: AsyncSession, ad: ConnectorAdapter) -> DimResult:
    """Re-fetch the source listing TODAY. 200 + parseable with real listings == connector alive.
    Ban interstitial, non-200, or an empty/zero-listing page == regression (connector may have rotted)."""
    try:
        r = await ad.module._get(sess, ad.access_url) if hasattr(ad.module, "_get") else await sess.get(ad.access_url, timeout=40)
    except Exception as e:  # noqa: BLE001
        return DimResult("access", FAIL, CRITICAL, f"live fetch raised {type(e).__name__}: {e}",
                         {"url": ad.access_url})
    text = r.text or ""
    low = text.lower()
    ban = next((t for t in _BAN_TELLS if t in low), None)
    if r.status_code != 200:
        return DimResult("access", FAIL, CRITICAL, f"HTTP {r.status_code} (was 200) — source blocked/moved",
                         {"status": r.status_code, "url": ad.access_url})
    if ban:
        return DimResult("access", FAIL, CRITICAL, f"ban/challenge interstitial detected ({ban!r})",
                         {"status": 200, "tell": ban})
    n, note = ad.parse_listing(text)
    if n == 0:
        return DimResult("access", FAIL, HIGH, f"200 but 0 listings parsed — connector parser rotted? ({note})",
                         {"status": 200, "bytes": len(text)})
    return DimResult("access", PASS, detail=f"200, {note}, {len(text)} bytes",
                     evidence={"status": 200, "listings": n, "bytes": len(text)})


async def _live_sample(conn, sess: AsyncSession, ad: ConnectorAdapter, ent: str,
                       sample_n: int) -> tuple[list[dict], dict]:
    """Pull a random sample of served rows, fetch EACH detail fresh, return (per-row diff results,
    counters). Shared by FIELD_VS_LIVE_DETAIL and PRICE_TRAP_LIVE so we fetch the live pages ONCE."""
    rows = await conn.fetch(
        "SELECT source_url, title, year, price, currency, mileage_km "
        "FROM entity_inventory WHERE entity_ulid=$1", ent)
    persisted = [dict(r) for r in rows]
    if not persisted:
        return [], {"served": 0, "fetched": 0, "gone": 0}
    pick = random.sample(persisted, min(sample_n, len(persisted)))
    results: list[dict] = []
    gone = 0
    for p in pick:
        url = p["source_url"]
        det = await ad.fetch_detail(sess, url)
        if det.get("status") in (404, 410) or det.get("fields") is None:
            gone += 1
            results.append({"url": url, "status": det.get("status"), "live": None,
                            "persisted": p, "diff": None})
        else:
            live = det["fields"]
            results.append({"url": url, "status": det.get("status"), "live": live,
                            "persisted": p, "diff": _diff_row(p, live)})
        await asyncio.sleep(SLEEP)
    return results, {"served": len(persisted), "fetched": len(pick), "gone": gone}


def dim_field_vs_live(results: list[dict], counters: dict) -> DimResult:
    """Diff each sampled row's persisted fields against its FRESH detail page, field-by-field.
    match-rate = matched fields / compared fields across the sample. High == data still true to source;
    low == drift (price/year/km moved) -> GAP carrying the concrete diffs. A 404 row = listing gone
    (delta should already have GONE-marked it; counted, not diffed)."""
    if counters["served"] == 0:
        return DimResult("field_vs_live_detail", FAIL, CRITICAL, "entity serves 0 rows to sample", counters)
    if counters["fetched"] == 0:
        return DimResult("field_vs_live_detail", NEEDS_LIVE, None, "no rows fetched", counters)
    total = matched = 0
    mismatches: list[dict] = []
    per_field_tot: dict[str, int] = {}
    per_field_ok: dict[str, int] = {}
    for res in results:
        diff = res.get("diff")
        if not diff:
            continue
        for fname, ok in diff["fields"].items():
            total += 1
            per_field_tot[fname] = per_field_tot.get(fname, 0) + 1
            if ok:
                matched += 1
                per_field_ok[fname] = per_field_ok.get(fname, 0) + 1
        if diff["mismatch"]:
            mismatches.append({"url": res["url"], **diff["mismatch"]})
    rate = round(matched / total, 4) if total else 0.0
    by_field = {f: f"{per_field_ok.get(f, 0)}/{per_field_tot[f]}" for f in sorted(per_field_tot)}
    ev = {"match_rate": rate, "fields_compared": total, "fields_matched": matched,
          "by_field": by_field, "sampled": counters["fetched"], "gone_404": counters["gone"],
          "served": counters["served"], "mismatches": mismatches[:10]}
    if total == 0:
        return DimResult("field_vs_live_detail", NEEDS_LIVE, None,
                         f"sampled {counters['fetched']} rows but live pages exposed no comparable "
                         f"fields ({counters['gone']} gone/404)", ev)
    if counters["gone"] == counters["fetched"]:
        return DimResult("field_vs_live_detail", GAP, HIGH,
                         f"ALL {counters['fetched']} sampled listings 404/gone — delta should have "
                         f"GONE-marked them (stale served set?)", ev)
    if rate < _MATCH_PASS:
        sev = HIGH if rate < 0.6 else MEDIUM
        return DimResult("field_vs_live_detail", GAP, sev,
                         f"field match-rate {rate*100:.1f}% < {_MATCH_PASS*100:.0f}% over "
                         f"{counters['fetched']} live pages (by_field={by_field}); persisted data drifted",
                         ev)
    detail = (f"match-rate {rate*100:.1f}% over {counters['fetched']} live detail pages "
              f"(by_field={by_field}, gone={counters['gone']})")
    return DimResult("field_vs_live_detail", PASS, detail=detail, evidence=ev)


def dim_price_trap_live(results: list[dict], ad: ConnectorAdapter) -> DimResult:
    """On the SAME fresh pages, confirm the served price equals the live CASH price the connector
    designates (its price_trap doctrine), NOT a monthly/lease figure. We compare the persisted price
    to the price the connector's OWN parser pulled from the live page (its cash node) — if they agree,
    the served price is provably the cash price the source shows today. A mismatch on price means the
    served figure no longer equals the source's cash node (drift or, worst case, a financing capture)."""
    priced = [r for r in results if r.get("live") and r["live"].get("price") is not None
              and r["persisted"].get("price") is not None]
    if not priced:
        return DimResult("price_trap_live", NEEDS_LIVE, None,
                         "no sampled page exposed both a persisted and a live cash price to compare",
                         {"trap_node": ad.price_trap_doc})
    agree = 0
    bad: list[dict] = []
    for r in priced:
        p = _norm_price(r["persisted"]["price"])
        l = _norm_price(r["live"]["price"])
        if p is not None and l is not None and p == l:
            agree += 1
        else:
            bad.append({"url": r["url"], "persisted": p, "live_cash": l})
    rate = round(agree / len(priced), 4)
    ev = {"cash_agreement": rate, "checked": len(priced), "agree": agree,
          "trap_node": ad.price_trap_doc, "disagreements": bad[:10]}
    if rate < _TRAP_PASS:
        return DimResult("price_trap_live", FAIL, CRITICAL,
                         f"served price == live CASH node only {rate*100:.1f}% of {len(priced)} pages — "
                         f"served price may not be the cash figure the source shows (trap/drift)", ev)
    return DimResult("price_trap_live", PASS,
                     detail=f"served price == live cash node on {agree}/{len(priced)} pages "
                            f"({rate*100:.0f}%); cash node = {ad.price_trap_doc[:60]}...",
                     evidence=ev)


async def dim_count_2way_live(sess: AsyncSession, ad: ConnectorAdapter) -> DimResult:
    """Re-derive the source's declared total two INDEPENDENT ways live (the connector's own
    ``count_verify``: an on-page/global counter vs a facet-partition sum). Returns the number so
    Layer 1's count_coverage can use a REAL declared figure instead of NEEDS_LIVE. The two ways must
    agree (quorum: a figure no two orthogonal paths confirm is humo) or this is a GAP."""
    try:
        declared, way2 = await ad.count_verify(sess)
    except Exception as e:  # noqa: BLE001
        return DimResult("count_2way_live", NEEDS_LIVE, None,
                         f"count_verify raised {type(e).__name__}: {e}", {})
    ev = {"declared": declared, "way2": way2}
    if not declared and not way2:
        return DimResult("count_2way_live", FAIL, HIGH,
                         "neither count path returned a number — source counter/facets moved", ev)
    if declared and way2:
        agree = 1 - abs(declared - way2) / max(declared, way2)
        ev["agreement"] = round(agree, 4)
        if agree < _COUNT_AGREE:
            return DimResult("count_2way_live", GAP, MEDIUM,
                             f"2-way count disagree: declared={declared} vs facet-sum={way2} "
                             f"({agree*100:.1f}% agree) — pick the conservative figure", ev)
        # The declared figure Layer 1 should use for count_coverage (the quorum-agreed total).
        ev["use_declared"] = min(declared, way2) if agree < 0.999 else declared
        return DimResult("count_2way_live", PASS,
                         detail=f"declared={declared} way2={way2} agree={agree*100:.1f}% "
                                f"-> count_coverage may use declared={ev['use_declared']}",
                         evidence=ev)
    # Only one path yielded a number — usable but not quorum-confirmed.
    single = declared or way2
    ev["use_declared"] = single
    return DimResult("count_2way_live", GAP, LOW,
                     f"only ONE count path returned a figure ({single}); not quorum-confirmed "
                     f"(declared={declared} way2={way2})", ev)


def dim_quorum(field_dim: DimResult, trap_dim: DimResult, count_dim: DimResult,
               *, fully_wired: bool = False) -> DimResult:
    """Skeptic quorum over the surviving live claims (VAM: a claim no two orthogonal paths confirm is
    not trustworthy). The orthogonal paths here are the THREE independent live dims above — each looks
    at the live source from a different angle (per-field detail diff, cash-price semantics, declared
    count). A claim of "this entity is live-faithful" earns quorum only if none of them FAILs.

    TODO(verify_entity_team): the full design spawns N independent skeptic sub-agents PER surviving
    served claim — each re-fetches that one listing with a fresh session/fingerprint and an independent
    parser, and the claim survives only on >=quorum agreement. That heavy fan-out belongs in the agent
    orchestrator (it needs the Agent runtime + cost budget, not a synchronous library call). This dim
    implements the deterministic floor of that idea — cross-confirmation across the 3 orthogonal live
    dims — and is honest that the per-claim multi-skeptic layer is not yet wired (status NEEDS_LIVE
    when asked to stand in for it). Dims 1-4 are fully live and runnable regardless."""
    survivors = [d for d in (field_dim, trap_dim, count_dim)]
    hard_fail = [d for d in survivors if d.status == FAIL]
    confirming = [d for d in survivors if d.status == PASS]
    ev = {"orthogonal_paths": {d.dim: d.status for d in survivors},
          "confirming": len(confirming), "failing": len(hard_fail),
          "per_claim_skeptics_wired": fully_wired}
    if hard_fail:
        return DimResult("quorum", FAIL, max((d.severity for d in hard_fail), key=_sev_rank),
                         f"{len(hard_fail)} orthogonal live path(s) FAIL "
                         f"({', '.join(d.dim for d in hard_fail)}) — claim not trustworthy", ev)
    if len(confirming) < 2:
        return DimResult("quorum", NEEDS_LIVE, None,
                         f"only {len(confirming)} orthogonal live path(s) PASS (need >=2 for quorum); "
                         f"per-claim multi-skeptic fan-out not yet wired (verify_entity_team TODO)", ev)
    return DimResult("quorum", PASS,
                     detail=f"{len(confirming)}/3 orthogonal live paths confirm, 0 fail "
                            f"(per-claim skeptic fan-out: {'wired' if fully_wired else 'TODO in team'})",
                     evidence=ev)


# ----------------------------------------------------------------------------------- orchestration
async def _resolve_entity(conn, *, domain: str) -> dict | None:
    row = await conn.fetchrow(
        "SELECT * FROM source_entities WHERE source_key=$1 OR domain=$1", domain)
    return dict(row) if row else None


async def verify_entity_live(domain: str | None = None, *, connector: str | None = None,
                             sample_n: int = SAMPLE_N, do_count: bool = True,
                             dsn: str = DSN) -> Verdict:
    """LIVE half of the entity verification. Returns a ``Verdict`` whose dims are the live dimensions,
    in the SAME shape Layer 1 emits — the future ``verify_entity_team`` concatenates ``verify_entity``
    (Layer 1) and this into one dim list and routes the union through ``gap_router``.

    This is also the function the orchestrator calls directly (no CLI) to get the live dims + the live
    declared count (in count_2way_live.evidence['use_declared']) to feed back into count_coverage."""
    dom, ad = _resolve_adapter(domain, connector)
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    try:
        async with pool.acquire() as conn:
            await conn.execute("SET max_parallel_workers_per_gather=0")
            ent = await _resolve_entity(conn, domain=dom)
            if not ent:
                v = Verdict(_entity_ulid(dom), dom, None)
                v.add(DimResult("access", FAIL, CRITICAL,
                                f"{dom} not in source_entities — nothing sealed to verify live", {}))
                return v
            ent_ulid = ent["entity_ulid"]
            v = Verdict(ent_ulid, ent.get("domain") or ent.get("source_key"), ent.get("kind"))
            async with AsyncSession(impersonate=IMPERSONATE) as sess:   # SESSION-level TLS, never per-req.
                # 1. ACCESS
                access = await dim_access(sess, ad)
                v.add(access)
                # 2+3. one live sample feeds both the field diff and the price-trap check.
                if access.status == FAIL:
                    # Source unreachable/banned: detail fetches are pointless; mark dependent dims LIVE-blocked.
                    v.add(DimResult("field_vs_live_detail", NEEDS_LIVE, None,
                                    "skipped — ACCESS failed (source unreachable today)", {}))
                    v.add(DimResult("price_trap_live", NEEDS_LIVE, None,
                                    "skipped — ACCESS failed (source unreachable today)", {}))
                    field_dim = v.dims[-2]
                    trap_dim = v.dims[-1]
                else:
                    results, counters = await _live_sample(conn, sess, ad, ent_ulid, sample_n)
                    field_dim = dim_field_vs_live(results, counters)
                    trap_dim = dim_price_trap_live(results, ad)
                    v.add(field_dim)
                    v.add(trap_dim)
                # 4. COUNT_2WAY_LIVE
                if do_count:
                    count_dim = await dim_count_2way_live(sess, ad)
                else:
                    count_dim = DimResult("count_2way_live", NEEDS_LIVE, None,
                                          "skipped (--no-count)", {})
                v.add(count_dim)
            # 5. QUORUM (synchronous cross-confirmation over the 3 orthogonal live dims)
            v.add(dim_quorum(field_dim, trap_dim, count_dim))
            v.served = await conn.fetchval(
                "SELECT count(*) FROM entity_inventory WHERE entity_ulid=$1", ent_ulid)
            return v
    finally:
        await pool.close()


def render(v: Verdict) -> str:
    """Live verdict block. Mirrors verifier.render so a reader sees Layer 1 and Layer 2 the same way."""
    icon = {PASS: "PASS", GAP: "GAP ", FAIL: "FAIL", NEEDS_LIVE: "LIVE"}
    head = (f"\n===== LIVE-VERIFY {v.domain}  ({v.entity_ulid[:16]}, kind={v.kind}, "
            f"served={v.served}) =====")
    lines = [head]
    for d in v.dims:
        sev = f" [{d.severity}]" if d.severity else ""
        lines.append(f"  [{icon.get(d.status, d.status)}] {d.dim:<22}{sev:<11} {d.detail}")
    if v.verified:
        verdict = "LIVE-VERIFIED ✓ (every live dimension PASS — persisted data matches the source today)"
    else:
        gaps = len(v.gaps)
        needs = sum(1 for d in v.dims if d.status == NEEDS_LIVE)
        verdict = (f"NOT LIVE-VERIFIED — {gaps} gap/fail" +
                   (f", {needs} needs-live" if needs else "") + " -> gap_router")
    lines.append(f"  ----> {verdict}")
    return "\n".join(lines)


async def _main() -> None:
    ap = argparse.ArgumentParser(description="Live (against-the-source) entity verification — Layer 2")
    ap.add_argument("--domain", help="source domain, e.g. autocasion.com")
    ap.add_argument("--connector", help="path to seal_<x>.py (used to infer domain when --domain omitted)")
    ap.add_argument("--sample", type=int, default=SAMPLE_N, help="detail pages to fetch fresh (default 8)")
    ap.add_argument("--no-count", action="store_true", help="skip the 2-way live count (faster)")
    a = ap.parse_args()
    v = await verify_entity_live(domain=a.domain, connector=a.connector,
                                 sample_n=a.sample, do_count=not a.no_count)
    print(render(v))


if __name__ == "__main__":
    asyncio.run(_main())
