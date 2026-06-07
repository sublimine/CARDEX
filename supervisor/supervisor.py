#!/usr/bin/env python3
"""cardex_supervisor — a pure-Python, long-running daemon that governs all CARDEX
workers 24/7, independent of any chat session.

Responsibilities:
  - Singleton: only one supervisor runs (own pidfile + liveness check).
  - Governs a config-driven registry of workers. Each worker: start command,
    PID + heartbeat healthcheck, restart with exponential backoff on death/hang.
  - Advances the 73 tier-1 queue via the `tier1_runner` worker (autonomous).
  - Writes supervisor_state.json (live workers, heartbeats, current portal,
    coverage) every tick. Rotates logs.

Pure Python, zero tokens. Launched + re-armed by Windows Task Scheduler
(boot trigger + 5-min healthcheck via ensure.py). RAM-bounded; never touches main.

Run directly:  python supervisor/supervisor.py
Stop:          delete supervisor/pids/supervisor.pid OR taskkill the PID; the
               Task Scheduler healthcheck will relaunch it unless unregistered.
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
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
PIDS = ROOT / "pids"
HB = ROOT / "hb"
LOGS = ROOT / "logs"
for d in (PIDS, HB, LOGS):
    d.mkdir(parents=True, exist_ok=True)

SUP_PID = PIDS / "supervisor.pid"
STATE = ROOT / "supervisor_state.json"
CONFIG = ROOT / "config.json"
SUP_LOG = LOGS / "supervisor.log"

TICK_S = 30
LOG_MAX_BYTES = 5_000_000
STILL_ACTIVE = 259

_k32 = ctypes.windll.kernel32 if os.name == "nt" else None


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if _k32 is None:
        try:
            os.kill(pid, 0); return True
        except Exception:
            return False
    PROCESS_QUERY_LIMITED = 0x1000
    h = _k32.OpenProcess(PROCESS_QUERY_LIMITED, False, int(pid))
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        _k32.GetExitCodeProcess(h, ctypes.byref(code))
        return code.value == STILL_ACTIVE
    finally:
        _k32.CloseHandle(h)


def log(msg: str) -> None:
    line = f"[{now_iso()}] {msg}\n"
    try:
        if SUP_LOG.exists() and SUP_LOG.stat().st_size > LOG_MAX_BYTES:
            SUP_LOG.replace(SUP_LOG.with_suffix(".log.1"))
        with SUP_LOG.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass
    sys.stdout.write(line); sys.stdout.flush()


def read_pidfile(p: Path) -> int | None:
    try:
        return int(p.read_text().strip())
    except Exception:
        return None


def hb_age(name: str) -> float | None:
    f = HB / f"{name}.hb"
    if not f.exists():
        return None
    return time.time() - f.stat().st_mtime


# --- singleton -------------------------------------------------------------------
def acquire_singleton() -> bool:
    existing = read_pidfile(SUP_PID)
    if existing and existing != os.getpid() and pid_alive(existing):
        log(f"another supervisor already running (pid={existing}); exiting.")
        return False
    SUP_PID.write_text(str(os.getpid()))
    return True


# --- worker governance -----------------------------------------------------------
class Worker:
    def __init__(self, cfg: dict):
        self.name = cfg["name"]
        self.cmd = cfg["cmd"]
        self.cwd = cfg.get("cwd", str(REPO))
        self.enabled = cfg.get("enabled", True)
        self.hb_max = cfg.get("heartbeat_max_age_s", 600)
        self.use_hb = cfg.get("use_heartbeat", True)
        self.backoff_base = cfg.get("backoff_base_s", 10)
        self.backoff_max = cfg.get("backoff_max_s", 600)
        self.pidfile = PIDS / f"{self.name}.pid"
        self.logfile = LOGS / f"{self.name}.log"
        self.fails = 0
        self.next_retry = 0.0
        self.last_start = None
        self.restarts = 0

    def pid(self) -> int | None:
        return read_pidfile(self.pidfile)

    def healthy(self) -> tuple[bool, str]:
        pid = self.pid()
        if not pid_alive(pid):
            return False, "dead"
        if self.use_hb:
            age = hb_age(self.name)
            if age is None:
                return True, "alive(no-hb-yet)"
            if age > self.hb_max:
                return False, f"hung(hb {int(age)}s>{self.hb_max})"
            return True, f"alive(hb {int(age)}s)"
        return True, "alive"

    def start(self) -> None:
        # kill any stale pid first
        pid = self.pid()
        if pid and pid_alive(pid):
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                               capture_output=True)
            except Exception:
                pass
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS
        env = dict(os.environ, PYTHONIOENCODING="utf-8",
                   CARDEX_WORKER=self.name, CARDEX_HB=str(HB / f"{self.name}.hb"))
        out = self.logfile.open("a", encoding="utf-8")
        try:
            p = subprocess.Popen(self.cmd, cwd=self.cwd, stdout=out, stderr=subprocess.STDOUT,
                                 creationflags=flags, env=env, close_fds=True)
            self.pidfile.write_text(str(p.pid))
            self.last_start = now_iso()
            self.restarts += 1
            log(f"started worker '{self.name}' pid={p.pid} (restart #{self.restarts})")
        except Exception as e:
            log(f"FAILED to start '{self.name}': {e}")

    def supervise(self) -> dict:
        ok, status = self.healthy()
        if not self.enabled:
            return {"name": self.name, "enabled": False, "status": "disabled", "pid": self.pid()}
        if ok:
            self.fails = 0
            return {"name": self.name, "enabled": True, "status": status, "pid": self.pid(),
                    "restarts": self.restarts, "last_start": self.last_start}
        # unhealthy → restart with backoff
        if time.time() >= self.next_retry:
            self.fails += 1
            backoff = min(self.backoff_base * (2 ** (self.fails - 1)), self.backoff_max)
            self.next_retry = time.time() + backoff
            log(f"worker '{self.name}' unhealthy ({status}); restarting (fail #{self.fails}, next backoff {backoff:.0f}s)")
            self.start()
            status = "restarting"
        else:
            status = f"down(backoff {int(self.next_retry - time.time())}s)"
        return {"name": self.name, "enabled": True, "status": status, "pid": self.pid(),
                "restarts": self.restarts, "fails": self.fails, "last_start": self.last_start}


def load_workers() -> list[Worker]:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    return [Worker(w) for w in cfg.get("workers", [])]


def read_tier1_progress() -> dict:
    f = REPO / "stealth" / "evidence" / "tier1_progress.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def main() -> int:
    if not acquire_singleton():
        return 0
    log(f"=== cardex_supervisor START pid={os.getpid()} ===")
    workers = load_workers()
    log(f"governing {len(workers)} workers: {[w.name for w in workers]}")
    try:
        while True:
            statuses = [w.supervise() for w in workers]
            state = {
                "supervisor_pid": os.getpid(),
                "ts": now_iso(),
                "tick_s": TICK_S,
                "workers": statuses,
                "tier1": read_tier1_progress(),
            }
            STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
            # refresh own pidfile (in case of adoption)
            SUP_PID.write_text(str(os.getpid()))
            time.sleep(TICK_S)
    except KeyboardInterrupt:
        log("supervisor stopped (KeyboardInterrupt)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
