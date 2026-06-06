#!/usr/bin/env python3
"""CARDEX control dashboard — generator entrypoint.

Reads the real system state and writes a self-contained HTML cockpit.
Designed to be run by the host scheduler every 15 minutes, or by hand.

Usage:
    python generate.py [--out PATH] [--json PATH]

The script is dependency-free (Python 3 stdlib only) and never raises on a
single source being down: unreachable collectors render as "sin datos".
It writes atomically (temp file + replace) so a half-written page is never
served to a browser that reloads mid-generation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

# allow `python dashboard/generate.py` from the repo root or from inside dashboard/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from collectors import collect_all  # noqa: E402
from render import render_html  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "cardex_control.html"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the CARDEX control dashboard")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output HTML path")
    parser.add_argument("--json", type=Path, default=None, help="also dump raw metrics JSON here")
    args = parser.parse_args(argv)

    started = datetime.now(timezone.utc)
    try:
        data = collect_all()
        html_out = render_html(data)
        _atomic_write(args.out, html_out)
        if args.json:
            _atomic_write(args.json, json.dumps(data, indent=2, ensure_ascii=False, default=str))
    except Exception:  # last-resort guard: log and exit non-zero, never crash silently
        sys.stderr.write("[cardex-dashboard] generation failed:\n")
        traceback.print_exc()
        return 1

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    pg_ok = data.get("pg", {}).get("available")
    sys.stdout.write(
        f"[cardex-dashboard] wrote {args.out} in {elapsed:.1f}s "
        f"(pg={'ok' if pg_ok else 'DOWN'}, "
        f"docker={'ok' if data.get('docker', {}).get('available') else 'DOWN'})\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
