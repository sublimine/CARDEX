"""
Adversarial discovery verification — distrust the harvester, prove no dealer is missing.

"CARDEX no vende mentiras": a harvester reporting "wrote N" is NOT proof we have all the
dealers. This re-derives the truth INDEPENDENTLY from the source and checks that every
single entity the source returns is actually in discovery_candidates — flagging any miss.

FR (registry:fr_sirene): for each sampled department, independently re-fetch the FULL set
of sirens for an activity code from recherche-entreprises (the source of truth) and verify
each siren exists in the DB. completeness = in_db / source_total per slice; any gap = the
exact sirens we dropped (which the caller re-harvests). This distrusts both the harvester's
count AND its coverage.

    python -m scripts.verify_discovery --fr-depts 75,69,13,48 --code 45.11Z
    python -m scripts.verify_discovery --fr-depts all --code 45.11Z   # full audit (slow)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os

import asyncpg
import httpx

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_FR_API = "https://recherche-entreprises.api.gouv.fr/search"
_HDR = {"Accept": "application/json", "User-Agent": "cardex-verify/1.0"}

_FR_DEPTS_ALL = (
    [f"{d:02d}" for d in range(1, 20)] + ["2A", "2B"]
    + [f"{d:02d}" for d in range(21, 96)] + ["971", "972", "973", "974", "976"]
)


async def _get(client: httpx.AsyncClient, params: dict, *, retries: int = 5) -> dict:
    """Robust GET — the verifier itself must not drop a page to a transient fault."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = await client.get(_FR_API, params=params, headers=_HDR)
            if r.status_code in (429, 502, 503, 504) and attempt < retries:
                await asyncio.sleep(1.0 * (2 ** attempt))
                continue
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001 — transient transport faults are retryable
            last = exc
            if attempt < retries:
                await asyncio.sleep(1.0 * (2 ** attempt))
                continue
            raise
    if last:
        raise last
    return {}


async def _source_records(client: httpx.AsyncClient, code: str, dept: str) -> dict[str, dict]:
    """Independently enumerate EVERY company the registry returns for (code, dept), by siren."""
    out: dict[str, dict] = {}
    page = 1
    while True:
        j = await _get(client, {"activite_principale": code, "departement": dept,
                                "per_page": 25, "page": page})
        res = j.get("results") or []
        if not res:
            break
        for x in res:
            s = (x.get("siren") or "").strip()
            if s:
                out[s] = x
        if page >= int(j.get("total_pages") or 1):
            break
        page += 1
    return out


async def _source_sirens(client: httpx.AsyncClient, code: str, dept: str) -> set[str]:
    return set((await _source_records(client, code, dept)).keys())


async def verify_fr(depts: list[str], code: str, *, fill: bool = False) -> dict:
    from scrapers.discovery.sources.mass_registry import _UPSERT_IDENTITY, fr_to_candidate

    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=8)
    per_dept: list[dict] = []
    total_src = total_db = total_filled = 0
    all_missing: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            for dept in depts:
                recs = await _source_records(client, code, dept)
                src = set(recs.keys())
                if not src:
                    per_dept.append({"dept": dept, "source": 0, "in_db": 0, "completeness": 1.0})
                    continue
                async with pool.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT registry_id FROM discovery_candidates "
                        "WHERE country='FR' AND source='registry:fr_sirene' "
                        "AND registry_id = ANY($1::text[])", list(src))
                in_db = {r["registry_id"] for r in rows}
                missing = src - in_db
                filled = 0
                if fill and missing:
                    for siren in missing:
                        cand = fr_to_candidate(recs[siren], code)
                        if not cand:
                            continue
                        try:
                            await pool.execute(
                                _UPSERT_IDENTITY, cand["country"], cand["source"], cand["name"],
                                cand["address"], cand["city"], cand["postcode"],
                                cand["registry_id"], json.dumps(cand["external_refs"]))
                            filled += 1
                        except Exception:  # noqa: BLE001
                            pass
                comp = len(in_db) / len(src)
                per_dept.append({"dept": dept, "source": len(src), "in_db": len(in_db),
                                 "missing": len(missing), "filled": filled, "completeness": round(comp, 4)})
                total_src += len(src); total_db += len(in_db); total_filled += filled
                all_missing.extend(list(missing)[:50])
                print(f"  dept {dept}: source={len(src)} in_db={len(in_db)} "
                      f"missing={len(missing)} filled={filled} completeness={comp:.1%}")
    finally:
        await pool.close()
    overall = (total_db / total_src) if total_src else 1.0
    verdict = "COMPLETE" if overall >= 0.999 else ("NEAR" if overall >= 0.95 else "GAP")
    return {"code": code, "depts": len(depts), "source_total": total_src, "in_db_total": total_db,
            "filled": total_filled, "completeness": round(overall, 4), "verdict": verdict,
            "missing_sample": all_missing[:50], "per_dept": per_dept}


async def _main() -> None:
    ap = argparse.ArgumentParser(description="Adversarial discovery completeness verification")
    ap.add_argument("--fr-depts", default="75,69,13,48", help="comma list or 'all'")
    ap.add_argument("--code", default="45.11Z")
    ap.add_argument("--fill", action="store_true", help="re-insert any missing siren (close the gap)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    depts = _FR_DEPTS_ALL if args.fr_depts.strip() == "all" else \
        [d.strip() for d in args.fr_depts.split(",") if d.strip()]
    print(f"FR adversarial verify: code={args.code} depts={len(depts)} fill={args.fill}")
    res = await verify_fr(depts, args.code, fill=args.fill)
    print("\nVERIFY " + json.dumps({k: v for k, v in res.items() if k != "per_dept"}, ensure_ascii=False))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    asyncio.run(_main())
