#!/usr/bin/env python3
"""CARDEX stealth harness — Camoufox-based evidence collector.

Given a URL, it launches the anti-detection browser (optionally with proxy /
geoip / humanized cursor), navigates, and reports HARD EVIDENCE:
  - final HTTP status + whether the page is a known anti-bot block
  - every XHR/fetch API response seen (url, status, bytes, content-type)
  - embedded Next.js/Nuxt state (__NEXT_DATA__ / __INITIAL_PROPS__) if present
  - page title, content length, screenshot, and HTML dump

This is the reusable workhorse for attacking JS/SPA + anti-bot portals. It never
concludes "blocked" without saving the evidence that shows it.

Usage:
    python harness.py URL [--proxy http://ip:port] [--no-geoip] [--wait MS]
                          [--capture-substr search/listing] [--label name]
RAM-safe: one browser instance, headless.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from pathlib import Path

EVID = Path(__file__).resolve().parent / "evidence"
EVID.mkdir(parents=True, exist_ok=True)

# Signatures of anti-bot interstitials (content / title heuristics).
BLOCK_SIGNS = [
    "datadome", "captcha-delivery", "geo.captcha",
    "access denied", "reference #", "akamai",
    "attention required", "cloudflare", "cf-chl", "challenge-platform",
    "px-captcha", "perimeterx", "_px", "human verification",
    "are you a robot", "unusual traffic", "blocked",
    "request unsuccessful", "incident id",
]


def classify(status: int | None, title: str, body: str) -> tuple[str, list[str]]:
    """Return (verdict, hits). verdict in {OK, BLOCKED, SUSPECT}."""
    low = (title + " " + body[:6000]).lower()
    hits = [s for s in BLOCK_SIGNS if s in low]
    if status and status >= 400:
        return "BLOCKED", hits or [f"http {status}"]
    if hits:
        # short page + block sign = blocked; long page may just mention the word
        if len(body) < 25000:
            return "BLOCKED", hits
        return "SUSPECT", hits
    if status == 200 and len(body) > 2000:
        return "OK", []
    return "SUSPECT", hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--proxy", default=None)
    ap.add_argument("--no-geoip", action="store_true")
    ap.add_argument("--wait", type=int, default=6000, help="extra ms to wait after load")
    ap.add_argument("--capture-substr", default=None, help="log response bodies whose URL contains this")
    ap.add_argument("--label", default="run")
    ap.add_argument("--warm", default=None, help="visit this URL first (warm cookies) before the target")
    ap.add_argument("--settle-rounds", type=int, default=0,
                    help="if blocked, retry N rounds of (wait+reload) to let JS challenges clear (Akamai/CF)")
    ap.add_argument("--settle-wait", type=int, default=9000, help="ms to wait per settle round")
    args = ap.parse_args()

    try:
        from camoufox.sync_api import Camoufox
    except Exception:
        print("IMPORT_FAIL"); traceback.print_exc(); return 2

    captured: list[dict] = []
    bodies: dict[str, str] = {}

    launch: dict = {"headless": True, "humanize": True}
    if not args.no_geoip:
        launch["geoip"] = True
    if args.proxy:
        launch["proxy"] = {"server": args.proxy}

    t0 = time.time()
    try:
        with Camoufox(**launch) as browser:
            page = browser.new_page()

            def on_response(resp):
                try:
                    url = resp.url
                    ct = resp.headers.get("content-type", "")
                    is_api = ("json" in ct) or any(
                        k in url for k in ("/api/", "graphql", "search", "listing", "/bff")
                    )
                    if is_api:
                        rec = {"url": url[:300], "status": resp.status, "ct": ct[:60]}
                        try:
                            rec["bytes"] = len(resp.body())
                        except Exception:
                            rec["bytes"] = None
                        captured.append(rec)
                        if args.capture_substr and args.capture_substr in url:
                            try:
                                bodies[url] = resp.text()[:200000]
                            except Exception:
                                pass
                except Exception:
                    pass

            page.on("response", on_response)

            if args.warm:
                try:
                    page.goto(args.warm, wait_until="domcontentloaded", timeout=60000)
                    # let the warm page clear its OWN JS challenge (sets _abck/cf cookies)
                    page.wait_for_timeout(16000)
                except Exception:
                    pass

            resp = None
            for attempt_n in range(2):
                try:
                    resp = page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
                    break
                except Exception as e:
                    print(f"  goto attempt {attempt_n+1} interrupted: {str(e)[:80]}")
                    page.wait_for_timeout(4000)
            status = resp.status if resp else None
            try:
                page.wait_for_timeout(args.wait)
            except Exception:
                pass

            title = page.title()
            body = page.content()
            verdict, hits = classify(status, title, body)

            # JS-challenge settle loop (Akamai/Cloudflare clear after sensor round-trip + reload)
            rounds = 0
            while verdict == "BLOCKED" and rounds < args.settle_rounds:
                rounds += 1
                try:
                    page.wait_for_timeout(args.settle_wait)
                    page.reload(wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(args.wait)
                except Exception:
                    pass
                title = page.title()
                body = page.content()
                verdict, hits = classify(status, title, body)
                print(f"  settle round {rounds}: verdict={verdict} len={len(body)} title={title[:40]!r}")

            # extract embedded SPA state
            next_data = None
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', body, re.DOTALL)
            if m:
                next_data = m.group(1)
            initial = None
            m2 = re.search(r'window\.__INITIAL_PROPS__\s*=\s*(\{.*?\})\s*</script>', body, re.DOTALL)
            if m2:
                initial = m2.group(1)

            stem = re.sub(r"[^a-z0-9]+", "_", args.label.lower()).strip("_")
            shot = EVID / f"{stem}.png"
            page.screenshot(path=str(shot), full_page=False)
            html_dump = EVID / f"{stem}.html"
            html_dump.write_text(body[:1500000], encoding="utf-8")

            print(f"URL={args.url}")
            print(f"HTTP_STATUS={status}")
            print(f"VERDICT={verdict}  block_signs={hits}")
            print(f"TITLE={title!r}")
            print(f"CONTENT_LEN={len(body)}")
            print(f"NEXT_DATA={'YES len='+str(len(next_data)) if next_data else 'no'}")
            print(f"INITIAL_PROPS={'YES len='+str(len(initial)) if initial else 'no'}")
            print(f"API_CALLS_SEEN={len(captured)}")
            for c in captured[:40]:
                print(f"  [{c['status']}] {c.get('bytes')}B {c['ct']}  {c['url']}")
            print(f"SCREENSHOT={shot}")
            print(f"HTML_DUMP={html_dump}")
            print(f"ELAPSED={time.time()-t0:.1f}s")

            if next_data:
                (EVID / f"{stem}_next_data.json").write_text(next_data[:2000000], encoding="utf-8")
            if initial:
                (EVID / f"{stem}_initial_props.json").write_text(initial[:2000000], encoding="utf-8")
            if captured:
                (EVID / f"{stem}_api_calls.json").write_text(
                    json.dumps(captured, indent=2, ensure_ascii=False), encoding="utf-8")
            if bodies:
                (EVID / f"{stem}_captured_bodies.json").write_text(
                    json.dumps(bodies, indent=2, ensure_ascii=False)[:2000000], encoding="utf-8")
                print(f"CAPTURED_BODIES={list(bodies.keys())}")

            return 0 if verdict == "OK" else (1 if verdict == "BLOCKED" else 0)
    except Exception:
        print(f"HARNESS_FAIL after {time.time()-t0:.1f}s"); traceback.print_exc(); return 3


if __name__ == "__main__":
    raise SystemExit(main())
