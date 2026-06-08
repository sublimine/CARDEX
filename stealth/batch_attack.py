#!/usr/bin/env python3
"""Sequential, RAM-safe (conc 1) Camoufox batch attacker.

Runs a list of portals one at a time (one browser at a time), each with warm-up +
anti-Akamai/CF settle loop, then extracts the embedded SSR state and reports the
listing count + sample. Writes evidence/batch_results.json incrementally so a
DETACHED run keeps a durable progress record across idle.

Designed to be launched detached (Start-Process -WindowStyle Hidden) so it
survives the session going idle.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import classify  # noqa: E402
from extract_state import extract_balanced, walk_find_lists, get_path  # noqa: E402

EVID = Path(__file__).resolve().parent / "evidence"
EVID.mkdir(parents=True, exist_ok=True)
RESULTS = EVID / "batch_results.json"

STATE_VARS = ["__NEXT_DATA__", "window.__INITIAL_PROPS__", "window.__INITIAL_STATE__",
              "window.__PRELOADED_STATE__", "window.__NUXT__", "window.__APOLLO_STATE__"]

TARGETS = [
    {"label": "kleinanzeigen", "url": "https://www.kleinanzeigen.de/s-autos/c216",
     "warm": "https://www.kleinanzeigen.de/", "settle": 3},
    {"label": "lacentrale", "url": "https://www.lacentrale.fr/listing",
     "warm": "https://www.lacentrale.fr/", "settle": 3},
    {"label": "gumtree", "url": "https://www.gumtree.com/cars",
     "warm": "https://www.gumtree.com/", "settle": 3},
    {"label": "as24_fr", "url": "https://www.autoscout24.fr/lst?atype=C&page=1&size=20&sort=standard",
     "warm": "https://www.autoscout24.fr/", "settle": 2},
    {"label": "as24_es", "url": "https://www.autoscout24.es/lst?atype=C&page=1&size=20&sort=standard",
     "warm": "https://www.autoscout24.es/", "settle": 2},
    {"label": "as24_nl", "url": "https://www.autoscout24.nl/lst?atype=C&page=1&size=20&sort=standard",
     "warm": "https://www.autoscout24.nl/", "settle": 2},
    {"label": "as24_be", "url": "https://www.autoscout24.be/lst?atype=C&page=1&size=20&sort=standard",
     "warm": "https://www.autoscout24.be/", "settle": 2},
    {"label": "as24_ch", "url": "https://www.autoscout24.ch/de/s?vehtyp=10",
     "warm": "https://www.autoscout24.ch/", "settle": 2},
]


def try_extract(html: str):
    """Return (var, path, count, sample) for the best listing array found."""
    best = None
    for var in STATE_VARS:
        raw = extract_balanced(html, var)
        if not raw:
            continue
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        lists = walk_find_lists(data)
        lists.sort(key=lambda t: t[1], reverse=True)
        if lists:
            path, n, _ = lists[0]
            try:
                arr = get_path(data, path)
            except Exception:
                arr = []
            sample = []
            for it in arr[:3]:
                if isinstance(it, dict):
                    sample.append({k: it.get(k) for k in
                                   ("id", "list_id", "title", "subject", "shortTitle", "price",
                                    "make", "model", "year", "km", "url", "relativeUrl")
                                   if k in it})
            cand = (var, path, n, sample, data)
            if best is None or n > best[2]:
                best = cand
    return best


def load_results() -> dict:
    if RESULTS.exists():
        try:
            return json.loads(RESULTS.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def run_one(browser, t: dict) -> dict:
    label, url = t["label"], t["url"]
    rec: dict = {"label": label, "url": url, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    page = browser.new_page()
    try:
        if t.get("warm"):
            try:
                page.goto(t["warm"], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(15000)
            except Exception:
                pass
        resp = None
        for _ in range(2):
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
                break
            except Exception:
                page.wait_for_timeout(4000)
        status = resp.status if resp else None
        page.wait_for_timeout(8000)
        title = page.title()
        body = page.content()
        verdict, hits = classify(status, title, body)
        rounds = 0
        while verdict == "BLOCKED" and rounds < t.get("settle", 0):
            rounds += 1
            try:
                page.wait_for_timeout(10000)
                page.reload(wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(8000)
            except Exception:
                pass
            title = page.title()
            body = page.content()
            verdict, hits = classify(status, title, body)
        # evidence
        (EVID / f"{label}.html").write_text(body[:1600000], encoding="utf-8")
        try:
            page.screenshot(path=str(EVID / f"{label}.png"))
        except Exception:
            pass
        rec.update({"status": status, "verdict": verdict, "block_signs": hits,
                    "title": title[:120], "content_len": len(body)})
        best = try_extract(body)
        if best:
            var, path, n, sample, data = best
            rec.update({"state_var": var, "listing_path": path, "listing_count": n, "sample": sample})
            (EVID / f"{label}_listings.json").write_text(
                json.dumps(get_path(data, path), ensure_ascii=False, indent=2)[:1500000], encoding="utf-8")
        else:
            rec["listing_count"] = 0
        return rec
    except Exception:
        rec["error"] = traceback.format_exc()[-800:]
        return rec
    finally:
        try:
            page.close()
        except Exception:
            pass


def main() -> int:
    from camoufox.sync_api import Camoufox
    only = sys.argv[1:]
    targets = [t for t in TARGETS if not only or t["label"] in only]
    results = load_results()
    for t in targets:
        print(f"\n### {t['label']} -> {t['url']}", flush=True)
        t0 = time.time()
        # fresh browser per portal (clean state, RAM released between)
        try:
            with Camoufox(headless=True, humanize=True, geoip=True) as browser:
                rec = run_one(browser, t)
        except Exception:
            rec = {"label": t["label"], "url": t["url"], "error": traceback.format_exc()[-800:]}
        rec["elapsed_s"] = round(time.time() - t0, 1)
        results[t["label"]] = rec
        RESULTS.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        v = rec.get("verdict"); n = rec.get("listing_count"); st = rec.get("status")
        print(f"    {t['label']}: status={st} verdict={v} listings={n} ({rec['elapsed_s']}s)", flush=True)
    print("\nBATCH DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
