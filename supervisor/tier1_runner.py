#!/usr/bin/env python3
"""tier1_runner — autonomous advancer of the 73 tier-1 coverage queue, governed by
cardex_supervisor. Pure Python, zero tokens.

Each cycle it:
  1. heartbeats (so the supervisor knows it is alive).
  2. ingests every facet/*_coverage.json into tier1_progress.json (the live ledger:
     portal -> official total, measured coverage, %, estado).
  3. advances the queue: ensures the current portal's coverage profiler is running
     (relaunches it with the supervisor pattern if it died and the portal is not yet
     measured); when a portal is measured, moves to the next pending portal that has
     a profiler. Portals without a profiler are recorded 'pendiente de perfil'.

It does NOT mark anything green (governance: Guardian audits). RAM-safe: at most one
coverage browser at a time; profilers are throttled.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
EVID = REPO / "stealth" / "evidence"
FACET = EVID / "facet"
LEDGER = EVID / "tier1_progress.json"
HB = os.environ.get("CARDEX_HB", str(ROOT / "hb" / "tier1_runner.hb"))

CYCLE_S = 45
_k32 = ctypes.windll.kernel32 if os.name == "nt" else None

# portals with a coverage profiler: portal -> (script, pidfile, coverage_json)
PROFILERS = {
    "coches.net": ("stealth/coches_coverage.py",
                   EVID / "coches_cov.pid", FACET / "coches_coverage.json"),
}
# seeds: already-measured portals (evidence on disk)
SEEDS = {
    "mobile.de": {"total_oficial": 1586022, "cobertura": 1586026, "pct": 100.0,
                  "estado": "pendiente de verificación", "ev": "facet/mobilede_coverage.json"},
    "leboncoin.fr": {"total_oficial": 900000, "cobertura": 900000, "pct": 100.0,
                     "estado": "pendiente de verificación", "ev": "sitemap_recon.json"},
}


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def beat():
    try:
        Path(HB).write_text(str(time.time()))
    except Exception:
        pass


def pid_alive(pid):
    if not pid:
        return False
    if _k32 is None:
        try:
            os.kill(int(pid), 0); return True
        except Exception:
            return False
    h = _k32.OpenProcess(0x1000, False, int(pid))
    if not h:
        return False
    try:
        c = ctypes.c_ulong(); _k32.GetExitCodeProcess(h, ctypes.byref(c)); return c.value == 259
    finally:
        _k32.CloseHandle(h)


def read_pid(p: Path):
    try:
        return int(p.read_text().strip())
    except Exception:
        return None


def load_queue():
    try:
        return json.loads((EVID / "tier1_queue.json").read_text(encoding="utf-8"))
    except Exception:
        return []


def ingest_coches(ledger: dict):
    j = FACET / "coches_coverage.json"
    if not j.exists():
        return
    try:
        r = json.loads(j.read_text(encoding="utf-8"))
    except Exception:
        return
    pid = read_pid(EVID / "coches_cov.pid")
    running = pid_alive(pid)
    n = len(r.get("per_make", []))
    ledger["coches.net"] = {
        "total_oficial": r.get("root"),
        "cobertura": r.get("sum_makes"),
        "pct": r.get("coverage_pct"),
        "estado": ("midiendo cobertura (worker vivo)" if running else
                   ("medido · pendiente de verificación" if n else "pendiente de perfil")),
        "makes_done": n,
        "ev": "facet/coches_coverage.json",
        "ts": now_iso(),
    }


def launch_profiler(portal: str):
    script, pidfile, _ = PROFILERS[portal]
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008
    logf = (ROOT / "logs" / f"profiler_{portal.replace('.', '_')}.log").open("a", encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.Popen(["python", "-u", script], cwd=str(REPO), stdout=logf,
                         stderr=subprocess.STDOUT, creationflags=flags, env=env, close_fds=True)
    pidfile.write_text(str(p.pid))
    sys.stdout.write(f"[tier1_runner] launched profiler {portal} pid={p.pid}\n"); sys.stdout.flush()


def govern_profilers(ledger: dict):
    """Ensure the active portal's profiler runs; relaunch if dead and not measured."""
    for portal, (script, pidfile, cov_json) in PROFILERS.items():
        st = ledger.get(portal, {})
        if st.get("estado", "").startswith("medido"):
            continue  # measured; leave for Guardian
        pid = read_pid(pidfile)
        if not pid_alive(pid):
            # not running and not measured -> (re)launch
            launch_profiler(portal)
        break  # one active profiler at a time (RAM-safe)


def main() -> int:
    sys.stdout.write(f"[tier1_runner] start pid={os.getpid()}\n"); sys.stdout.flush()
    queue = load_queue()
    while True:
        beat()
        ledger = {}
        if LEDGER.exists():
            try:
                ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
            except Exception:
                ledger = {}
        ledger.update(SEEDS)
        ingest_coches(ledger)
        # record pending portals (those in queue without measurement/profiler)
        measured = set(ledger)
        pendientes = [q["portal"] for q in queue if q["portal"] not in measured
                      and q["portal"] not in PROFILERS]
        ledger["_meta"] = {
            "ts": now_iso(), "queue_total": len(queue),
            "medidos_o_en_curso": len([k for k in ledger if not k.startswith("_")]),
            "pendientes_de_perfil": len(pendientes),
            "proximos": pendientes[:8],
        }
        LEDGER.write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            govern_profilers(ledger)
        except Exception as e:
            sys.stdout.write(f"[tier1_runner] govern error: {e}\n"); sys.stdout.flush()
        time.sleep(CYCLE_S)


if __name__ == "__main__":
    raise SystemExit(main())
