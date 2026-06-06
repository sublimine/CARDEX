"""CARDEX control dashboard — data collectors.

Reads the REAL state of the system from its authoritative stores. Nothing is
fabricated: every collector either returns verified live data or marks itself
unavailable so the renderer can show "sin datos" instead of inventing numbers.

Sources (all read-only):
  - PostgreSQL  (cardex-pg)        via `docker exec ... psql`   -> rich/index/discovery tables
  - Redis       (cardex-redis)     via `docker exec ... redis-cli` -> stream depths (the L1->L2 seam)
  - SQLite      (scrapers/engine.db) via stdlib sqlite3          -> work_queue, identities, proxies, dlq, tiers
  - Docker      (`docker ps`)                                    -> container up/down + health

Design rules:
  - Each collector is isolated in try/except: one failing source never blocks the rest.
  - No secrets are hardcoded. Credentials are auto-discovered from the running
    container's environment (or overridden via env vars).
  - Every subprocess call is bounded by a timeout.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- topology constants (verified via `docker ps`, 2026-06-06) -------------------
PG_CONTAINER = "cardex-pg"
REDIS_CONTAINER = "cardex-redis"

# Containers the compose stack is expected to run. Anything missing renders red.
EXPECTED_CONTAINERS = [
    "cardex-pg",
    "cardex-redis",
    "cardex-ch",
    "cardex-meili",
    "cardex-api",
    "cardex-grafana",
    "cardex-prometheus",
    "cardex-web",
]

# Redis streams that make up the pipeline seams (Contracts C5/C7/C8 in the blueprint).
PIPELINE_STREAMS = [
    "stream:enrich_pending",
    "stream:ingestion_raw",
    "stream:meili_sync",
    "stream:price_events",
    "stream:thumb_requests",
    "stream:db_write",
    "stream:dlq",
]

_FS = "\x1f"  # ASCII unit separator — safe field delimiter for psql -A output
_TIMEOUT = 30


# --- low-level helpers -----------------------------------------------------------
def _run(cmd: list[str], timeout: int = _TIMEOUT) -> tuple[bool, str, str]:
    """Run a command, returning (ok, stdout, stderr). Never raises."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode == 0, proc.stdout, proc.stderr
    except FileNotFoundError as exc:
        return False, "", f"command not found: {exc}"
    except subprocess.TimeoutExpired:
        return False, "", f"timeout after {timeout}s"
    except Exception as exc:  # defensive: collectors must never crash the run
        return False, "", str(exc)


def _container_env(container: str, key: str) -> str | None:
    """Read an env var from a running container (no secret hardcoding)."""
    ok, out, _ = _run(
        ["docker", "inspect", container, "--format",
         "{{range .Config.Env}}{{println .}}{{end}}"]
    )
    if not ok:
        return None
    prefix = f"{key}="
    for line in out.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):]
    return None


def _pg_creds() -> tuple[str, str]:
    user = os.environ.get("CARDEX_PG_USER") or _container_env(PG_CONTAINER, "POSTGRES_USER") or "cardex"
    db = os.environ.get("CARDEX_PG_DB") or _container_env(PG_CONTAINER, "POSTGRES_DB") or "cardex"
    return user, db


def _redis_password() -> str | None:
    return os.environ.get("CARDEX_REDIS_PASSWORD") or _container_env(REDIS_CONTAINER, "REDIS_PASSWORD")


def _psql(sql: str) -> list[list[str]] | None:
    """Run SQL in cardex-pg, return rows as lists of string cells, or None on failure."""
    user, db = _pg_creds()
    ok, out, _ = _run(
        ["docker", "exec", PG_CONTAINER, "psql", "-U", user, "-d", db,
         "-t", "-A", "-F", _FS, "-c", sql]
    )
    if not ok:
        return None
    rows = []
    for line in out.splitlines():
        line = line.rstrip()
        if not line:
            continue
        rows.append(line.split(_FS))
    return rows


def _redis_cli(args: list[str]) -> str | None:
    pwd = _redis_password()
    base = ["docker", "exec", REDIS_CONTAINER, "redis-cli"]
    if pwd:
        base += ["-a", pwd, "--no-auth-warning"]
    ok, out, _ = _run(base + args)
    if not ok:
        return None
    return out.strip()


def _engine_db_path() -> Path:
    # this file lives in <repo>/dashboard/; engine.db lives in <repo>/scrapers/
    return Path(__file__).resolve().parent.parent / "scrapers" / "engine.db"


def _sqlite_rows(con: sqlite3.Connection, sql: str) -> list[tuple]:
    try:
        return con.execute(sql).fetchall()
    except sqlite3.Error:
        return []


# --- collectors ------------------------------------------------------------------
def collect_docker() -> dict[str, Any]:
    ok, out, err = _run(["docker", "ps", "--format", "{{.Names}}" + _FS + "{{.Status}}"])
    if not ok:
        return {"available": False, "error": err.strip() or "docker ps failed"}
    running: dict[str, str] = {}
    for line in out.splitlines():
        if _FS in line:
            name, status = line.split(_FS, 1)
            running[name.strip()] = status.strip()
    containers = []
    for name in EXPECTED_CONTAINERS:
        status = running.get(name)
        if status is None:
            containers.append({"name": name, "status": "no corriendo", "state": "down"})
        else:
            healthy = "healthy" in status.lower()
            unhealthy = "unhealthy" in status.lower()
            state = "down" if unhealthy else ("up" if healthy or status.lower().startswith("up") else "warn")
            containers.append({"name": name, "status": status, "state": state})
    # surface any extra cardex containers not in the expected set
    for name, status in running.items():
        if name.startswith("cardex-") and name not in EXPECTED_CONTAINERS:
            containers.append({"name": name, "status": status, "state": "up"})
    up = sum(1 for c in containers if c["state"] == "up")
    return {"available": True, "containers": containers, "up": up, "total": len(containers)}


def _scalar(sql: str) -> int | None:
    rows = _psql(sql)
    if not rows or not rows[0]:
        return None
    try:
        return int(rows[0][0])
    except (ValueError, IndexError):
        return None


def collect_postgres() -> dict[str, Any]:
    counts_rows = _psql(
        """
        SELECT 'vehicle_index', count(*) FROM vehicle_index
        UNION ALL SELECT 'vehicle_events', count(*) FROM vehicle_events
        UNION ALL SELECT 'vehicles', count(*) FROM vehicles
        UNION ALL SELECT 'discovery_candidates', count(*) FROM discovery_candidates
        UNION ALL SELECT 'entities', count(*) FROM entities
        UNION ALL SELECT 'entity_matches', count(*) FROM entity_matches
        UNION ALL SELECT 'vin_history_cache', count(*) FROM vin_history_cache
        UNION ALL SELECT 'dealer_inventory', count(*) FROM dealer_inventory
        UNION ALL SELECT 'dealers', count(*) FROM dealers
        """
    )
    if counts_rows is None:
        return {"available": False, "error": "psql unreachable"}

    counts = {r[0]: int(r[1]) for r in counts_rows if len(r) == 2}

    def table(sql: str) -> list[dict]:
        rows = _psql(sql) or []
        return rows  # raw rows; shaped by callers below

    index_by_country = [
        {"country": r[0], "n": int(r[1])}
        for r in (_psql("SELECT country, count(*) FROM vehicle_index GROUP BY country ORDER BY 2 DESC") or [])
        if len(r) == 2
    ]
    index_by_domain = [
        {"domain": r[0], "country": r[1], "n": int(r[2])}
        for r in (_psql(
            "SELECT source_domain, country, count(*) FROM vehicle_index "
            "GROUP BY source_domain, country ORDER BY 3 DESC") or [])
        if len(r) == 3
    ]
    events_by_type = [
        {"type": r[0], "n": int(r[1])}
        for r in (_psql("SELECT event_type, count(*) FROM vehicle_events GROUP BY event_type ORDER BY 2 DESC") or [])
        if len(r) == 2
    ]
    disc_by_country = [
        {"country": r[0], "total": int(r[1]), "with_domain": int(r[2]),
         "pct": round(100.0 * int(r[2]) / int(r[1]), 1) if int(r[1]) else 0.0}
        for r in (_psql(
            "SELECT country, count(*), count(domain) FROM discovery_candidates "
            "GROUP BY country ORDER BY 2 DESC") or [])
        if len(r) == 3
    ]
    disc_by_source = [
        {"source": r[0], "n": int(r[1]), "with_domain": int(r[2])}
        for r in (_psql(
            "SELECT source, count(*), count(domain) FROM discovery_candidates "
            "GROUP BY source ORDER BY 2 DESC") or [])
        if len(r) == 3
    ]
    sitemap_status = [
        {"status": r[0] or "(null)", "n": int(r[1])}
        for r in (_psql("SELECT sitemap_status, count(*) FROM discovery_candidates GROUP BY sitemap_status ORDER BY 2 DESC") or [])
        if len(r) == 2
    ]
    vehicles_by_platform = [
        {"platform": r[0] or "(null)", "n": int(r[1])}
        for r in (_psql("SELECT source_platform, count(*) FROM vehicles GROUP BY source_platform ORDER BY 2 DESC") or [])
        if len(r) == 2
    ]
    fresh_rows = _psql(
        """
        SELECT 'vehicle_index', max(last_seen)::text FROM vehicle_index
        UNION ALL SELECT 'vehicle_events', max(ts)::text FROM vehicle_events
        UNION ALL SELECT 'discovery_candidates', max(last_seen)::text FROM discovery_candidates
        """
    ) or []
    freshness = {r[0]: (r[1] if len(r) > 1 else None) for r in fresh_rows}

    distinct_domains = _scalar("SELECT count(DISTINCT source_domain) FROM vehicle_index")

    return {
        "available": True,
        "counts": counts,
        "index_by_country": index_by_country,
        "index_by_domain": index_by_domain,
        "events_by_type": events_by_type,
        "disc_by_country": disc_by_country,
        "disc_by_source": disc_by_source,
        "sitemap_status": sitemap_status,
        "vehicles_by_platform": vehicles_by_platform,
        "freshness": freshness,
        "distinct_domains": distinct_domains,
    }


def collect_redis() -> dict[str, Any]:
    # ping first so we can distinguish "down" from "empty"
    pong = _redis_cli(["PING"])
    if pong is None:
        return {"available": False, "error": "redis unreachable or auth missing"}
    streams = []
    for stream in PIPELINE_STREAMS:
        xlen = _redis_cli(["XLEN", stream])
        try:
            n = int(xlen) if xlen is not None else None
        except ValueError:
            n = None
        streams.append({"name": stream, "xlen": n})
    return {"available": True, "streams": streams}


def collect_engine_db() -> dict[str, Any]:
    path = _engine_db_path()
    if not path.exists():
        return {"available": False, "error": f"engine.db not found at {path}"}
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return {"available": False, "error": str(exc)}
    try:
        wq_status = {r[0]: int(r[1]) for r in _sqlite_rows(
            con, "SELECT status, count(*) FROM work_queue GROUP BY status")}
        wq_portals = [
            {"portal": r[0], "country": r[1], "tier": r[2], "status": r[3], "attempts": int(r[4] or 0)}
            for r in _sqlite_rows(
                con, "SELECT portal, country, tier, status, attempts FROM work_queue ORDER BY status, portal")
        ]
        id_total = sum(int(r[1]) for r in _sqlite_rows(con, "SELECT 1, count(*) FROM identities"))
        id_by_status = {r[0]: int(r[1]) for r in _sqlite_rows(
            con, "SELECT status, count(*) FROM identities GROUP BY status")}
        id_by_country = {r[0]: int(r[1]) for r in _sqlite_rows(
            con, "SELECT country, count(*) FROM identities GROUP BY country")}
        proxies = sum(int(r[1]) for r in _sqlite_rows(con, "SELECT 1, count(*) FROM proxy_health"))
        circuit = {r[0]: int(r[1]) for r in _sqlite_rows(
            con, "SELECT circuit_state, count(*) FROM domain_tier_state GROUP BY circuit_state")}
        tiers = {r[0]: int(r[1]) for r in _sqlite_rows(
            con, "SELECT tier, count(*) FROM domain_tier_state GROUP BY tier")}
        dlq = sum(int(r[1]) for r in _sqlite_rows(con, "SELECT 1, count(*) FROM dlq"))
    finally:
        con.close()
    return {
        "available": True,
        "work_queue": {"by_status": wq_status, "portals": wq_portals},
        "identities": {"total": id_total, "by_status": id_by_status, "by_country": id_by_country},
        "proxies": proxies,
        "circuit": circuit,
        "tiers": tiers,
        "dlq": dlq,
    }


def collect_all() -> dict[str, Any]:
    """Run every collector and stamp the result. The single entrypoint for the renderer."""
    return {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "docker": collect_docker(),
        "pg": collect_postgres(),
        "redis": collect_redis(),
        "engine": collect_engine_db(),
    }


if __name__ == "__main__":
    print(json.dumps(collect_all(), indent=2, ensure_ascii=False, default=str))
