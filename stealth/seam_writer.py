#!/usr/bin/env python3
"""Wire the stealth delta into the REAL CARDEX seam.

Takes normalised records (from facet_engine / dump_worker) and reconciles them
against the previous snapshot, then writes idempotently to the live seam:
  - SEEN (new url_hash)  -> INSERT vehicle_index (ON CONFLICT DO NOTHING, C3)
                          + vehicle_events 'SEEN' (C4)
                          + XADD stream:enrich_pending {h,u,s,c} (C5)
  - GONE (disappeared)   -> DELETE vehicle_index + vehicle_events 'GONE'

Injection-safe: scraped text is untrusted, so rows are loaded via `\\copy ... CSV`
(csv-escaped) into a temp table, never string-concatenated into SQL.

Local discipline: validate-with-limit-and-purge. `--limit N` caps the sample;
`--purge` removes the sample from the seam afterwards (full dump = VPS). PG/Redis
are reached via `docker exec` (no host driver dependency).

Usage:
    python seam_writer.py --records evidence/dumps/leboncoin_harvest.jsonl \\
        --source leboncoin.fr --country FR --limit 60 [--purge]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

PG = "cardex-pg"
REDIS = "cardex-redis"
EVID = Path(__file__).resolve().parent / "evidence"
SNAP = EVID / "seam_snapshots"
SNAP.mkdir(parents=True, exist_ok=True)


def psql(sql: str) -> tuple[bool, str]:
    """Run a single read/DML statement via -c, UTF-8 safe."""
    cmd = ["docker", "exec", "-i", PG, "psql", "-U", "cardex", "-d", "cardex",
           "-v", "ON_ERROR_STOP=1", "-t", "-A", "-c", sql]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def psql_script(script: str) -> tuple[bool, str]:
    """Feed a full multi-statement script (incl. inline \\copy FROM STDIN ... \\.)
    to psql via stdin. UTF-8 safe."""
    cmd = ["docker", "exec", "-i", PG, "psql", "-U", "cardex", "-d", "cardex", "-v", "ON_ERROR_STOP=1"]
    p = subprocess.run(cmd, input=script, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def redis_xadd_batch(entries: list[dict]) -> int:
    """XADD each SEEN pointer to stream:enrich_pending {h,u,s,c}."""
    if not entries:
        return 0
    lines = []
    for e in entries:
        # redis-cli args are passed via a piped command file; values are quoted
        lines.append("XADD stream:enrich_pending MAXLEN ~ 5000000 * "
                     f"h {sh(e['h'])} u {sh(e['u'])} s {sh(e['s'])} c {sh(e['c'])}")
    script = "\n".join(lines) + "\n"
    cmd = ["docker", "exec", "-i", REDIS, "redis-cli", "-a", "cardex_dev_only", "--no-auth-warning"]
    p = subprocess.run(cmd, input=script, capture_output=True, text=True)
    return script.count("XADD") if p.returncode == 0 else 0


def sh(v: str) -> str:
    # quote a redis-cli inline value (no spaces/newlines in our hashes/urls except url)
    return "'" + str(v).replace("'", "") + "'"


def load_records(path: Path, limit: int | None) -> list[dict]:
    recs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        recs.append(json.loads(line))
        if limit and len(recs) >= limit:
            break
    return recs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True, type=Path)
    ap.add_argument("--source", required=True)
    ap.add_argument("--country", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--purge", action="store_true")
    args = ap.parse_args()

    recs = load_records(args.records, args.limit)
    if not recs:
        print("no records"); return 1
    cur = {r["url_hash"]: r for r in recs}
    snap_file = SNAP / f"{args.source}.json"
    prev = set(json.loads(snap_file.read_text(encoding="utf-8"))) if snap_file.exists() else set()
    seen = [h for h in cur if h not in prev]       # altas
    gone = [h for h in prev if h not in cur]        # bajas
    print(f"records={len(recs)} prev_snapshot={len(prev)} SEEN(altas)={len(seen)} GONE(bajas)={len(gone)}")

    # 1) load current SEEN rows into a temp table via injection-safe inline CSV copy
    if seen:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        for h in seen:
            r = cur[h]
            w.writerow([h, r.get("source_url", ""), args.source, args.country[:2],
                        (r.get("title") or "")[:300], r.get("price_eur") if isinstance(r.get("price_eur"), (int, float)) else "",
                        r.get("mileage_km") if isinstance(r.get("mileage_km"), int) else "",
                        r.get("year") if isinstance(r.get("year"), int) else ""])
        script = (
            "CREATE TEMP TABLE _stage(url_hash text,url_original text,source_domain text,country char(2),"
            "titulo_modelo text,precio numeric,kilometraje int,anio smallint);\n"
            "\\copy _stage FROM STDIN WITH (FORMAT csv)\n"
            + buf.getvalue()
            + "\\.\n"
            "INSERT INTO vehicle_index(url_hash,url_original,source_domain,country,sitemap_source,titulo_modelo,precio,kilometraje,anio) "
            "SELECT url_hash,url_original,source_domain,country,'stealth',titulo_modelo,precio,kilometraje,anio FROM _stage "
            "ON CONFLICT (url_hash) DO NOTHING;\n"
            "INSERT INTO vehicle_events(url_hash,url_original,source_domain,country,sitemap_source,event_type,titulo_modelo,precio,kilometraje,anio) "
            "SELECT url_hash,url_original,source_domain,country,'stealth','SEEN',titulo_modelo,precio,kilometraje,anio FROM _stage;\n"
        )
        ok, msg = psql_script(script)
        print(f"  INSERT vehicle_index + SEEN events: {'OK' if ok else 'FAIL'} {msg[:200]}")
        # XADD enrich_pending for SEEN
        xs = redis_xadd_batch([{"h": h, "u": cur[h].get("source_url", ""), "s": args.source, "c": args.country[:2]} for h in seen])
        print(f"  XADD stream:enrich_pending: {xs} messages")

    # 2) GONE -> delete + GONE event
    if gone:
        gph = ",".join("'" + h.replace("'", "") + "'" for h in gone)  # hashes are hex[:32], safe
        ok, msg = psql(
            f"INSERT INTO vehicle_events(url_hash,source_domain,country,event_type) "
            f"SELECT url_hash,source_domain,country,'GONE' FROM vehicle_index WHERE url_hash IN ({gph});\n"
            f"DELETE FROM vehicle_index WHERE url_hash IN ({gph});")
        print(f"  GONE delete + events: {'OK' if ok else 'FAIL'} {msg[:160]}")

    # snapshot update
    snap_file.write_text(json.dumps(sorted(cur.keys())), encoding="utf-8")

    # verify in seam
    ok, n = psql(f"SELECT count(*) FROM vehicle_index WHERE source_domain='{args.source}';")
    print(f"  vehicle_index[{args.source}] now = {n}")
    ok, ev = psql(f"SELECT event_type,count(*) FROM vehicle_events WHERE source_domain='{args.source}' GROUP BY event_type;")
    print(f"  vehicle_events[{args.source}]: {ev.replace(chr(10),' | ')}")

    # local purge (validate-with-limit-and-purge)
    if args.purge:
        ok, msg = psql(f"DELETE FROM vehicle_index WHERE source_domain='{args.source}' AND sitemap_source='stealth';")
        print(f"  PURGED local sample (sitemap_source='stealth'): {'OK' if ok else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
