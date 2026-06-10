"""
host_budget — S-HOST: the single host-global resource broker for the CARDEX fleet.

The fleet runs many independent Python processes (probe, resolve, harvest,
discovery) on ONE modest host (a laptop: AMD Ryzen 5 5500U, 6c/12t, integrated
GPU with no usable inference acceleration, ~4 GB free RAM). Historically each
script enforced its OWN RAM and concurrency caps, so two or three overlapping
runs collectively blew past the real budget. That was the physical root cause of
the 2026-06-10 "DEAD epidemic" (the home resolver/NAT saturated under several
concurrent network runs and fabricated hundreds of false DEAD verdicts) and of
the host OOM-killing the sibling API at ~585 MB free.

S-HOST lifts those per-script caps into ONE host-global broker that every heavy
worker consults BEFORE doing work, so the box can never be saturated or shut
down regardless of how many workflows run:

  * RAM gate      — available physical MB vs SOFT/HARD thresholds (OS-global).
  * Disk gate     — free GB on the working volume (slice-then-purge keeps it healthy).
  * Conc budget   — a CROSS-PROCESS slot semaphore via PG advisory locks, which
                    are session-scoped and auto-release if a worker crashes, so a
                    dead process never leaks a slot.
  * Thermal proxy — the box exposes no readable ACPI temperature sensor, so a
                    sustained 100 % pin (what thermally shuts a laptop down) is
                    prevented structurally by the concurrency lanes plus an
                    optional RAM/CPU cooldown — never by reading degrees we can't.

Lanes (tuned to this host; override via env):
  BROWSER <= 2  — Camoufox/Chromium are the RAM killers (E07 once spawned ~20 -> OOM).
  NET     <= 8  — curl_cffi is light and network-bound; the cap bounds in-flight.
  LLM     <= 1  — Ollama qwen2.5:3b runs on CPU (no GPU); one model resident, serialized.

Doctrine: PG advisory locks only (no coordination state in Redis, which stays a
Streams transport); no UPDATE of unmutated rows; if PG is unreachable the broker
fails DEGRADED to a process-local cap (still bounded) — never fail-open to "no cap".
"""
from __future__ import annotations

import asyncio
import contextlib
import gc
import os
import shutil
import sys

# ---- thresholds: single source of truth, env-overridable --------------------
RAM_SOFT_MB = int(os.environ.get("CARDEX_RAM_SOFT_MB", "750"))   # below: halve concurrency
RAM_HARD_MB = int(os.environ.get("CARDEX_RAM_HARD_MB", "550"))   # below: pause / abort heavy work
DISK_MIN_GB = float(os.environ.get("CARDEX_DISK_MIN_GB", "8"))   # below: pause harvest (purge first)
WORK_VOLUME = os.environ.get("CARDEX_WORK_VOLUME", "C:\\" if sys.platform == "win32" else "/")

LANE_BUDGET: dict[str, int] = {
    "browser": int(os.environ.get("CARDEX_LANE_BROWSER", "2")),
    "net": int(os.environ.get("CARDEX_LANE_NET", "8")),
    "llm": int(os.environ.get("CARDEX_LANE_LLM", "1")),
}
# One advisory-lock namespace per lane (first int of PG's 2-int advisory API).
_LANE_NS: dict[str, int] = {"browser": 0x435801, "net": 0x435802, "llm": 0x435803}
_DEFAULT_NS = 0x435800

_LOCAL_SEMS: dict[str, asyncio.Semaphore] = {}


# ---- RAM / disk: OS-global, no external dependency --------------------------
def available_mb() -> int:
    """Available physical RAM in MB. Windows-native (GlobalMemoryStatusEx);
    Linux /proc/meminfo; psutil only as a last fallback for the eventual VPS."""
    if sys.platform == "win32":
        import ctypes

        class _M(ctypes.Structure):
            _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong),
                        ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                        ("tpf", ctypes.c_ulonglong), ("apf", ctypes.c_ulonglong),
                        ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong),
                        ("ae", ctypes.c_ulonglong)]

        m = _M()
        m.l = ctypes.sizeof(_M)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return int(m.ap // 1024 // 1024)  # ullAvailPhys
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    try:
        import psutil  # type: ignore
        return int(psutil.virtual_memory().available // 1024 // 1024)
    except Exception:
        return 10_000  # unknown -> assume healthy so the RAM gate is a no-op, never a false stall


def disk_free_gb(path: str = WORK_VOLUME) -> float:
    try:
        return shutil.disk_usage(path).free / (1024 ** 3)
    except OSError:
        return 999.0


def ram_state() -> str:
    """OK | SOFT | HARD."""
    mb = available_mb()
    if mb < RAM_HARD_MB:
        return "HARD"
    if mb < RAM_SOFT_MB:
        return "SOFT"
    return "OK"


def throttle_reason() -> str | None:
    """Non-None means the host is under pressure and callers must pause new heavy work."""
    if ram_state() == "HARD":
        return f"RAM_HARD<{RAM_HARD_MB}MB(avail={available_mb()})"
    free = disk_free_gb()
    if free < DISK_MIN_GB:
        return f"DISK_LOW<{DISK_MIN_GB}GB(free={free:.1f})"
    return None


def effective_conc(requested: int) -> int:
    """Concurrency the host can afford right now: full if OK, halved if SOFT, 0 if HARD."""
    st = ram_state()
    if st == "HARD":
        return 0
    if st == "SOFT":
        return max(2, requested // 2)
    return requested


async def wait_until_healthy(*, poll_s: float = 5.0, max_s: float = 180.0) -> bool:
    """Block (GC + poll) until RAM/disk pressure clears. True if healthy, False on timeout."""
    waited = 0.0
    while True:
        if throttle_reason() is None:
            return True
        gc.collect()
        if waited >= max_s:
            return False
        await asyncio.sleep(poll_s)
        waited += poll_s


def _local_sem(lane: str, budget: int) -> asyncio.Semaphore:
    sem = _LOCAL_SEMS.get(lane)
    if sem is None:
        sem = asyncio.Semaphore(budget)
        _LOCAL_SEMS[lane] = sem
    return sem


@contextlib.asynccontextmanager
async def slot(pool, lane: str, *, poll_s: float = 1.0, max_wait_s: float = 120.0):
    """
    Acquire ONE host-global slot in `lane` (cross-process) for the `async with` body.

    Uses PG advisory locks so the cap holds across every process on the host; the
    lock is session-scoped, so if this worker crashes the slot frees automatically.
    A dedicated pool connection is held for the slot's lifetime (advisory locks ride
    the connection's session) — size the pool for sum(LANE_BUDGET)+headroom, or pass
    a small dedicated coordination pool.

    Degrades to a process-local semaphore when `pool` is None (PG unreachable): the
    process is still capped, never uncapped.
    """
    budget = LANE_BUDGET.get(lane, 4)
    if pool is None:
        sem = _local_sem(lane, budget)
        await sem.acquire()
        try:
            yield None
        finally:
            sem.release()
        return

    ns = _LANE_NS.get(lane, _DEFAULT_NS)
    conn = await pool.acquire()
    got = -1
    waited = 0.0
    try:
        while True:
            for slot_id in range(budget):
                if await conn.fetchval("SELECT pg_try_advisory_lock($1,$2)", ns, slot_id):
                    got = slot_id
                    break
            if got >= 0 or waited >= max_wait_s:
                break
            await asyncio.sleep(poll_s)
            waited += poll_s
        yield got  # got == -1 means the host is full and we proceeded degraded after max_wait
    finally:
        if got >= 0:
            await conn.fetchval("SELECT pg_advisory_unlock($1,$2)", ns, got)
        await pool.release(conn)
