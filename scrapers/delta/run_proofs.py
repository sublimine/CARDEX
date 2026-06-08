"""End-to-end PROOFS for the delta-always-on + alert + auto-remediation front.

PROOF 1 — always-on delta: push a harvest batch with a NEW url, measure the time until it
          appears in /v1/entities/{ulid}/delta; then a complete cycle without it -> GONE.
PROOF 2 — exact-point alert: emit a volume_drift alert, show the persisted operator_alerts
          row (entity + stage + signal + evidence).
PROOF 3 — dispatcher call-site: the remediation_dispatcher consumes the operator_event and
          invokes the (previously orphan) remediate(), recovering the entity.

Run (host): REDIS_URL points at the host-reachable throwaway redis; PG is the canonical store.
    DATABASE_URL=postgresql://cardex:cardex_dev_only@localhost:5432/cardex \
    REDIS_URL=redis://localhost:56390 \
    python -m scrapers.delta.run_proofs
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import urllib.request
from pathlib import Path

import asyncpg
import redis.asyncio as aioredis

from scrapers.delta import delta_worker, operator_events, remediation_dispatcher
from scrapers.pipeline.generic_extractor import FetchResult
from scrapers.portals import config as cfgmod
from scrapers.portals.config import DriftBaseline, Endpoints, ExtractionConfig

PG_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:56390")
API = os.environ.get("ENTITY_API", "http://127.0.0.1:8088")


# ── fakes (mirror scrapers/tests/test_dealer_remediation.py — no network) ──────────────
class MapFetcher:
    def __init__(self, pages):
        self._pages = pages

    async def __call__(self, url: str) -> FetchResult:
        if url in self._pages:
            status, body = self._pages[url]
            return FetchResult(url=url, status_code=status, body=body)
        return FetchResult(url=url, status_code=404, body=b"")


def _b(t: str) -> bytes:
    return t.encode("utf-8")


_PAD = "<div class='spec'><span></span></div>" * 600


def _jsonld() -> bytes:
    return _b(
        "<html><head><script type=\"application/ld+json\">"
        '{"@context":"https://schema.org","@type":"Car","brand":{"name":"BMW"},'
        '"model":"320d","vehicleModelDate":"2019","image":["https://cdn.d.example/1.jpg"],'
        '"offers":{"price":"24900","priceCurrency":"EUR"}}'
        "</script></head><body>" + _PAD + "</body></html>")


def _sitemap_pages(domain: str):
    loc = f"https://{domain}/vehicles/bmw-320d-1"
    sm = f"<urlset><url><loc>{loc}</loc></url></urlset>"
    return {
        f"https://{domain}/robots.txt": (200, _b(f"Sitemap: https://{domain}/sitemap.xml")),
        f"https://{domain}/sitemap.xml": (200, _b(sm)),
        loc: (200, _jsonld()),
    }


def _seam(persisted):
    async def run(domain, country, urls, is_e07):
        return persisted
    return run


async def _purge(urls):
    return len(urls)


def _fake_deps(domain):
    return {"static_fetcher": MapFetcher(_sitemap_pages(domain)), "e07_fetcher": None,
            "seam_runner": _seam(1), "purger": _purge}


# ── helpers ────────────────────────────────────────────────────────────────────────────
def _api_get(path: str) -> dict:
    try:
        with urllib.request.urlopen(API + path, timeout=8) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:  # entity not created yet during the poll race
            return {"data": []}
        raise


async def _poll_api_delta(ulid: str, url: str, etype: str, timeout: float = 20.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        data = await asyncio.to_thread(_api_get, f"/v1/entities/{ulid}/delta?limit=30")
        for ev in data["data"]:
            if ev["source_url"] == url and ev["event_type"] == etype:
                return time.monotonic()
        await asyncio.sleep(0.1)
    return None


# ── PROOF 1 ──────────────────────────────────────────────────────────────────────────
async def proof1(pool, rdb) -> None:
    domain = "delta-test.example"
    ulid = operator_events.entity_ulid_for(domain)
    await pool.execute("DELETE FROM vehicle_events WHERE source_domain=$1", domain)
    await pool.execute("DELETE FROM vehicle_index WHERE source_domain=$1", domain)
    # Pre-create the entity so the API /delta endpoint resolves during the poll race
    # (the worker would also create it on first insert; this removes the startup window).
    await pool.execute(
        "INSERT INTO source_entities(entity_ulid,source_key,kind,domain,country,defense_tier) "
        "VALUES($1,$2,'platform',$2,'DE','T2') ON CONFLICT(source_key) DO NOTHING", ulid, domain)
    await delta_worker.ensure_group(rdb, delta_worker.HARVEST_STREAM, delta_worker.GROUP)

    worker = asyncio.create_task(delta_worker.run())   # always-on consumer
    await asyncio.sleep(0.6)                            # let it subscribe
    try:
        url = f"https://{domain}/car/{int(time.time())}"
        t0 = time.monotonic()
        await delta_worker.push_batch(rdb, source_key=domain, country="DE", domain=domain,
                                      urls=[url], complete=False)
        seen = await _poll_api_delta(ulid, url, "SEEN")
        alta_ms = round((seen - t0) * 1000) if seen else None

        t1 = time.monotonic()
        await delta_worker.push_batch(rdb, source_key=domain, country="DE", domain=domain,
                                      urls=[f"https://{domain}/car/keep"], complete=True)
        gone = await _poll_api_delta(ulid, url, "GONE")
        baja_ms = round((gone - t1) * 1000) if gone else None
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass

    api = await asyncio.to_thread(_api_get, f"/v1/entities/{ulid}/delta?limit=5")
    print("\n=== PROOF 1 — DELTA ALWAYS-ON (push → visible in /v1/entities/{ulid}/delta) ===")
    print(f"entity_ulid = {ulid}  (delta-test.example)")
    print(f"ALTA  latency push→SEEN-in-API = {alta_ms} ms")
    print(f"BAJA  latency push→GONE-in-API = {baja_ms} ms")
    print("API /delta now returns:", json.dumps(api["data"][:3], indent=2, default=str))


# ── PROOF 2 ──────────────────────────────────────────────────────────────────────────
async def proof2(pool) -> tuple[int, str]:
    domain = "remediate-test.example"
    ulid = operator_events.entity_ulid_for(domain)
    await pool.execute(
        "INSERT INTO source_entities(entity_ulid,source_key,kind,domain,country,defense_tier) "
        "VALUES($1,$2,'dealer',$2,'DE','T2') ON CONFLICT(source_key) DO UPDATE SET country='DE'",
        ulid, domain)
    alert_id = await operator_events.emit_alert(
        source_key=domain, stage="extract", signal="volume_drift", severity="warning",
        evidence={"volume": 3, "expected_min": 50, "reason": "harvest 3 < baseline 50"})
    row = await pool.fetchrow(
        "SELECT alert_id,entity_ulid,source_key,stage,signal,severity,status,evidence,created_at "
        "FROM operator_alerts WHERE alert_id=$1", alert_id)
    print("\n=== PROOF 2 — ALERT PINPOINTS THE EXACT FAILURE POINT ===")
    print(f"operator_alerts row (alert_id={alert_id}):")
    print(json.dumps({k: (str(v) if not isinstance(v, (int, str, type(None))) else v)
                      for k, v in dict(row).items()}, indent=2, default=str))
    api = await asyncio.to_thread(_api_get, "/v1/alerts?signal=volume_drift&limit=1")
    print("API /v1/alerts returns:", json.dumps(api["data"][:1], indent=2, default=str))
    return alert_id, domain


# ── PROOF 3 ──────────────────────────────────────────────────────────────────────────
async def proof3(pool, rdb, domain: str) -> None:
    tmp = Path(tempfile.mkdtemp())
    (tmp / "portals").mkdir()
    cfgmod._DEALER_DIR = tmp
    cfgmod._CONFIG_DIR = tmp / "portals"
    cfgmod.save(ExtractionConfig(
        source_key=domain, country="DE", strategy="sitemap_listing", version=2,
        endpoints=Endpoints(host="www." + domain),
        drift_baseline=DriftBaseline(expected_min_volume=50)), kind="dealer")

    await remediation_dispatcher.ensure_group(
        rdb, remediation_dispatcher.EVENTS_STREAM, remediation_dispatcher.GROUP)
    before = await pool.fetchrow(
        "SELECT alert_id,status FROM operator_alerts WHERE source_key=$1 ORDER BY alert_id DESC LIMIT 1",
        domain)
    await remediation_dispatcher.run(
        oneshot=True, max_idle_polls=3, deps_provider=lambda: _fake_deps(domain))
    after = await pool.fetchrow(
        "SELECT alert_id,status,remediation_action,remediation_result,attempts "
        "FROM operator_alerts WHERE source_key=$1 ORDER BY alert_id DESC LIMIT 1", domain)
    print("\n=== PROOF 3 — DISPATCHER CONSUMES EVENT → INVOKES remediate() (real call-site) ===")
    print(f"alert BEFORE: {dict(before)}")
    print(f"alert AFTER : status={after['status']} action={after['remediation_action']} "
          f"attempts={after['attempts']}")
    print(f"remediation_result: {after['remediation_result']}")


async def main() -> None:
    pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=4)
    rdb = aioredis.from_url(REDIS_URL, decode_responses=False)
    try:
        await proof1(pool, rdb)
        _alert_id, domain = await proof2(pool)
        await proof3(pool, rdb, domain)
    finally:
        await rdb.aclose()
        await pool.close()
    print("\nALL 3 PROOFS COMPLETE.")


if __name__ == "__main__":
    asyncio.run(main())
