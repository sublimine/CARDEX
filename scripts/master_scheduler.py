"""
CARDEX master scheduler — orchestrates the full discovery+enrich+refresh cycle.

Runs forever. Each phase logs its state to /tmp/cardex-logs and reports to
the scheduler log. Any phase that dies is restarted on the next cycle.

Phase schedule:
    discovery orchestrator       every 24h
    sitemap_resolver             every  6h (drains new pending rows)
    sitemap_bridge               every  6h (re-drains found sitemaps)
    sitemap_image_harvester      every 12h
    meili_enricher (8 shards)    always (if dead, restart)
    repair_pass                  always (if dead, restart)
    country_backfill             every 12h
    quality_audit (read-only)    every  1h

Usage:
    nohup python -u scripts/master_scheduler.py > /tmp/cardex-logs/scheduler.log 2>&1 &
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [sched] %(message)s",
)
log = logging.getLogger("sched")

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = Path("/tmp/cardex-logs")
PID_DIR = Path("/tmp/cardex-pids")
LOG_DIR.mkdir(exist_ok=True)
PID_DIR.mkdir(exist_ok=True)

# env inherited by children
CHILD_ENV = {
    **os.environ,
    "DATABASE_URL": os.environ.get(
        "DATABASE_URL",
        "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
    ),
    "MEILI_URL": os.environ.get("MEILI_URL", "http://localhost:7700"),
    "MEILI_MASTER_KEY": os.environ.get("MEILI_MASTER_KEY", "cardex_meili_dev_only"),
    "PYTHONPATH": str(ROOT),
}

# Job catalog: (name, module, env overrides, period_seconds, long_running)
# long_running=True → keep it alive always (like enricher shards)
# long_running=False → run once then sleep period_seconds
JOBS: list[tuple] = [
    # always-on workers
    ("enrich_s0", "scrapers.discovery.meili_enricher",
     {"MEILI_ENRICHER_SHARD": "0", "MEILI_ENRICHER_SHARDS": "8",
      "MEILI_ENRICHER_CONC": "50", "MEILI_ENRICHER_TIMEOUT": "6"}, 0, True),
    ("enrich_s1", "scrapers.discovery.meili_enricher",
     {"MEILI_ENRICHER_SHARD": "1", "MEILI_ENRICHER_SHARDS": "8",
      "MEILI_ENRICHER_CONC": "50", "MEILI_ENRICHER_TIMEOUT": "6"}, 0, True),
    ("enrich_s2", "scrapers.discovery.meili_enricher",
     {"MEILI_ENRICHER_SHARD": "2", "MEILI_ENRICHER_SHARDS": "8",
      "MEILI_ENRICHER_CONC": "50", "MEILI_ENRICHER_TIMEOUT": "6"}, 0, True),
    ("enrich_s3", "scrapers.discovery.meili_enricher",
     {"MEILI_ENRICHER_SHARD": "3", "MEILI_ENRICHER_SHARDS": "8",
      "MEILI_ENRICHER_CONC": "50", "MEILI_ENRICHER_TIMEOUT": "6"}, 0, True),
    ("enrich_s4", "scrapers.discovery.meili_enricher",
     {"MEILI_ENRICHER_SHARD": "4", "MEILI_ENRICHER_SHARDS": "8",
      "MEILI_ENRICHER_CONC": "50", "MEILI_ENRICHER_TIMEOUT": "6"}, 0, True),
    ("enrich_s5", "scrapers.discovery.meili_enricher",
     {"MEILI_ENRICHER_SHARD": "5", "MEILI_ENRICHER_SHARDS": "8",
      "MEILI_ENRICHER_CONC": "50", "MEILI_ENRICHER_TIMEOUT": "6"}, 0, True),
    ("enrich_s6", "scrapers.discovery.meili_enricher",
     {"MEILI_ENRICHER_SHARD": "6", "MEILI_ENRICHER_SHARDS": "8",
      "MEILI_ENRICHER_CONC": "50", "MEILI_ENRICHER_TIMEOUT": "6"}, 0, True),
    ("enrich_s7", "scrapers.discovery.meili_enricher",
     {"MEILI_ENRICHER_SHARD": "7", "MEILI_ENRICHER_SHARDS": "8",
      "MEILI_ENRICHER_CONC": "50", "MEILI_ENRICHER_TIMEOUT": "6"}, 0, True),
    ("repair", "scrapers.discovery.repair_pass",
     {"REPAIR_CONC": "10", "REPAIR_BATCH": "300"}, 0, True),
    # periodic jobs
    ("sitemap_resolver", "scrapers.discovery.sitemap_resolver",
     {"SITEMAP_RESOLVER_CONCURRENCY": "30"}, 6 * 3600, False),
    ("country_backfill", "scrapers.discovery.country_backfill",
     {}, 12 * 3600, False),
    ("quality_audit", "scrapers.discovery.quality_audit",
     {}, 3600, False),
]


class Job:
    def __init__(self, name, module, env_override, period, long_running):
        self.name = name
        self.module = module
        self.env = {**CHILD_ENV, **env_override}
        self.period = period
        self.long_running = long_running
        self.last_started = 0.0
        self.proc: subprocess.Popen | None = None

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def should_start(self) -> bool:
        if self.long_running:
            return not self.is_alive()
        if self.is_alive():
            return False
        return time.monotonic() - self.last_started >= self.period

    def start(self) -> None:
        log_path = LOG_DIR / f"{self.name}.log"
        log.info("starting %s", self.name)
        fp = log_path.open("a", encoding="utf-8")
        fp.write(f"\n----- {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} starting -----\n")
        fp.flush()
        self.proc = subprocess.Popen(
            [sys.executable, "-u", "-m", self.module],
            cwd=str(ROOT),
            env=self.env,
            stdout=fp,
            stderr=subprocess.STDOUT,
        )
        self.last_started = time.monotonic()
        (PID_DIR / f"{self.name}.pid").write_text(str(self.proc.pid))

    def status(self) -> str:
        if self.is_alive():
            return f"{self.name}=UP({self.proc.pid})"
        return f"{self.name}=DOWN"


def main() -> None:
    jobs = [Job(*j) for j in JOBS]

    def handle_sigterm(signum, frame):
        log.info("SIGTERM — shutting down all jobs")
        for j in jobs:
            if j.is_alive():
                j.proc.terminate()
        time.sleep(3)
        for j in jobs:
            if j.is_alive():
                j.proc.kill()
        sys.exit(0)

    try:
        signal.signal(signal.SIGTERM, handle_sigterm)
    except (AttributeError, ValueError):
        pass

    log.info("master scheduler starting — %d jobs", len(jobs))
    while True:
        for j in jobs:
            try:
                if j.should_start():
                    j.start()
            except Exception as exc:
                log.error("job %s start error: %s", j.name, exc)
        if int(time.time()) % 120 == 0:
            status = " ".join(j.status() for j in jobs)
            log.info("status: %s", status)
        time.sleep(30)


if __name__ == "__main__":
    main()
