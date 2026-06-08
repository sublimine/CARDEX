#!/usr/bin/env python3
"""Idempotent supervisor launcher — the entrypoint Windows Task Scheduler runs at
boot and every 5 minutes. If the supervisor is already alive, exit. Otherwise
launch it detached. This is the outer healthcheck that makes the daemon survive
crashes, logout and reboot. Pure Python, instant, zero tokens."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
SUP_PID = ROOT / "pids" / "supervisor.pid"
SUP = ROOT / "supervisor.py"
LOG = ROOT / "logs" / "ensure.log"
ROOT.joinpath("pids").mkdir(parents=True, exist_ok=True)
ROOT.joinpath("logs").mkdir(parents=True, exist_ok=True)


def pid_alive(pid):
    if not pid:
        return False
    if os.name != "nt":
        try:
            os.kill(int(pid), 0); return True
        except Exception:
            return False
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
    if not h:
        return False
    try:
        c = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(c))
        return c.value == 259
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def main() -> int:
    pid = None
    try:
        pid = int(SUP_PID.read_text().strip())
    except Exception:
        pid = None
    if pid_alive(pid):
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"supervisor alive pid={pid}; nothing to do\n")
        return 0
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008 if os.name == "nt" else 0
    out = (ROOT / "logs" / "supervisor.out").open("a", encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.Popen([sys.executable, "-u", str(SUP)], cwd=str(REPO),
                         stdout=out, stderr=subprocess.STDOUT, creationflags=flags,
                         env=env, close_fds=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"launched supervisor pid={p.pid}\n")
    sys.stdout.write(f"launched supervisor pid={p.pid}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
