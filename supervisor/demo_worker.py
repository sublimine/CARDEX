#!/usr/bin/env python3
"""Minimal governed worker — heartbeats every few seconds. Exists to demonstrate
supervisor governance: kill it and the supervisor restarts it (with a fresh PID
and resumed heartbeat). Pure Python, trivial RAM."""
from __future__ import annotations
import os, sys, time
from pathlib import Path

HB = os.environ.get("CARDEX_HB")
NAME = os.environ.get("CARDEX_WORKER", "demo_worker")


def beat():
    if HB:
        try:
            Path(HB).write_text(str(time.time()))
        except Exception:
            pass


def main() -> int:
    sys.stdout.write(f"[demo_worker] start pid={os.getpid()}\n"); sys.stdout.flush()
    while True:
        beat()
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
