#!/usr/bin/env python3
"""Camoufox smoke test — does the anti-detection browser even LAUNCH on this
Windows + Application Control host, and can it render a real page?

Evidence-first: prints HTTP status, page title, a content fingerprint, and saves
a screenshot. No verdict without proof.
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

EVID = Path(__file__).resolve().parent / "evidence"
EVID.mkdir(parents=True, exist_ok=True)


def main() -> int:
    try:
        from camoufox.sync_api import Camoufox
    except Exception:
        print("IMPORT_FAIL")
        traceback.print_exc()
        return 2

    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    t0 = time.time()
    try:
        # headless, single instance, modest timeouts; RAM-safe
        with Camoufox(headless=True, humanize=True) as browser:
            page = browser.new_page()
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            status = resp.status if resp else None
            title = page.title()
            body = page.content()
            shot = EVID / "smoke.png"
            page.screenshot(path=str(shot))
            print(f"LAUNCH_OK url={url}")
            print(f"HTTP_STATUS={status}")
            print(f"TITLE={title!r}")
            print(f"CONTENT_LEN={len(body)}")
            print(f"CONTENT_HEAD={body[:200]!r}")
            print(f"SCREENSHOT={shot}")
            print(f"ELAPSED={time.time()-t0:.1f}s")
            return 0
    except Exception:
        print(f"LAUNCH_FAIL after {time.time()-t0:.1f}s")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
