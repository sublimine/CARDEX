#!/usr/bin/env python3
"""Sitemap-first reconnaissance for the cracked giants.

For each portal: robots.txt -> Sitemap: entries -> sitemap index -> listing
sitemaps -> count <url> entries. This measures the FULL deposit size (how many
ad URLs exist) without paginating search ad-by-ad.

Network layer only (curl_cffi, residential IP) — no browser, RAM-cheap. Handles
gzip sitemaps. Reports hard numbers; flags anti-bot blocks for browser fallback.

Usage:
    python sitemap_recon.py            # all default portals
    python sitemap_recon.py https://www.mobile.de
"""
from __future__ import annotations

import gzip
import io
import re
import sys
import time
from pathlib import Path

from curl_cffi import requests as cr

EVID = Path(__file__).resolve().parent / "evidence"
EVID.mkdir(parents=True, exist_ok=True)

PORTALS = [
    "https://www.mobile.de",
    "https://www.coches.net",
    "https://www.leboncoin.fr",
    "https://www.autoscout24.de",
    "https://www.autoscout24.fr",
    "https://www.autoscout24.es",
    "https://www.autoscout24.nl",
    "https://www.autoscout24.be",
    "https://www.autoscout24.ch",
]

# url substrings that suggest a sitemap of vehicle DETAIL pages
LISTING_HINTS = ("listing", "/ad", "ads", "vehicle", "fahrzeug", "inserat", "detail",
                 "car", "coche", "voiture", "occasion", "gebraucht", "annonce", "search", "srp")

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "de-DE,de;q=0.9,en;q=0.8,fr;q=0.7,es;q=0.6",
}
IMP = "chrome131"


def fetch(url: str, timeout: int = 30):
    return cr.get(url, headers=HEADERS, impersonate=IMP, timeout=timeout)


def decode_xml(resp) -> str:
    raw = resp.content
    if raw[:2] == b"\x1f\x8b" or url_is_gz(resp.url):
        try:
            raw = gzip.decompress(raw)
        except Exception:
            try:
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            except Exception:
                pass
    return raw.decode("utf-8", errors="replace")


def url_is_gz(url: str) -> bool:
    return url.lower().split("?")[0].endswith(".gz")


def locs(xml: str) -> list[str]:
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)


def is_index(xml: str) -> bool:
    return "<sitemapindex" in xml


def robots_sitemaps(base: str) -> tuple[int, list[str], str]:
    try:
        r = fetch(base.rstrip("/") + "/robots.txt")
    except Exception as e:
        return -1, [], f"EXC {e}"
    if r.status_code != 200:
        return r.status_code, [], r.text[:120]
    sm = re.findall(r"(?im)^\s*Sitemap:\s*(\S+)", r.text)
    return 200, sm, ""


def classify_block(resp) -> str | None:
    low = (resp.text[:3000]).lower()
    for s in ("datadome", "captcha", "akamai", "access denied", "cloudflare", "attention required", "blocked"):
        if s in low:
            return s
    if resp.status_code in (403, 429, 503):
        return f"http {resp.status_code}"
    return None


def recon(base: str) -> dict:
    host = re.sub(r"^https?://", "", base).strip("/")
    print(f"\n========== {host} ==========")
    out = {"host": host, "sitemaps": [], "listing_url_estimate": None, "blocked": None}
    status, sitemaps, err = robots_sitemaps(base)
    print(f"robots.txt: HTTP {status}  sitemaps_declared={len(sitemaps)}  {err[:80]}")
    for s in sitemaps[:12]:
        print(f"  declared: {s}")
    if not sitemaps:
        # common fallbacks
        sitemaps = [base.rstrip("/") + "/sitemap.xml"]
        print("  (no robots sitemaps; trying /sitemap.xml)")

    # process each declared sitemap (index or direct)
    total_listing_sitemaps = 0
    sampled = None
    sample_count = 0
    seen_children = 0
    for sm_url in sitemaps:
        try:
            r = fetch(sm_url)
        except Exception as e:
            print(f"  [{sm_url}] EXC {e}")
            continue
        blk = classify_block(r)
        if blk:
            print(f"  [{sm_url}] BLOCKED ({blk}) status={r.status_code}")
            out["blocked"] = blk
            continue
        if r.status_code != 200:
            print(f"  [{sm_url}] HTTP {r.status_code}")
            continue
        xml = decode_xml(r)
        if is_index(xml):
            children = locs(xml)
            seen_children += len(children)
            listing_children = [c for c in children if any(h in c.lower() for h in LISTING_HINTS)]
            total_listing_sitemaps += len(listing_children)
            print(f"  [INDEX {sm_url}] children={len(children)}  listing-like={len(listing_children)}")
            for c in (listing_children or children)[:3]:
                print(f"      e.g. {c}")
            # sample one listing child
            target = (listing_children or children)
            if target and sampled is None:
                try:
                    rc = fetch(target[0])
                    if rc.status_code == 200:
                        cxml = decode_xml(rc)
                        if is_index(cxml):
                            # nested index
                            gchildren = locs(cxml)
                            print(f"      nested index: {len(gchildren)} children")
                            if gchildren:
                                rg = fetch(gchildren[0])
                                if rg.status_code == 200:
                                    sample_count = len(locs(decode_xml(rg)))
                                    sampled = gchildren[0]
                        else:
                            sample_count = len(locs(cxml))
                            sampled = target[0]
                except Exception as e:
                    print(f"      sample EXC {e}")
        else:
            n = len(locs(xml))
            print(f"  [URLSET {sm_url}] url_count={n}")
            if sampled is None:
                sampled = sm_url
                sample_count = n

    if sampled:
        print(f"  SAMPLE listing sitemap: {sampled}  urls={sample_count}")
    out["sitemaps"] = sitemaps
    out["listing_sitemaps"] = total_listing_sitemaps
    out["sample_sitemap"] = sampled
    out["sample_url_count"] = sample_count
    if total_listing_sitemaps and sample_count:
        est = total_listing_sitemaps * sample_count
        out["listing_url_estimate"] = est
        print(f"  >>> ESTIMATE: {total_listing_sitemaps} listing-sitemaps x ~{sample_count} urls = ~{est:,} ad URLs")
    elif sample_count:
        out["listing_url_estimate"] = sample_count
        print(f"  >>> at least {sample_count:,} ad URLs in sampled sitemap")
    return out


def main() -> int:
    targets = sys.argv[1:] or PORTALS
    results = []
    for base in targets:
        try:
            results.append(recon(base))
        except Exception as e:
            print(f"  RECON FAIL {base}: {e}")
        time.sleep(1)
    print("\n\n===== SUMMARY =====")
    for r in results:
        est = r.get("listing_url_estimate")
        est_s = f"~{est:,}" if est else "n/a"
        blk = f" BLOCKED:{r['blocked']}" if r.get("blocked") else ""
        print(f"  {r['host']:<26} listing_urls={est_s:<14} sample={r.get('sample_url_count')}{blk}")
    import json
    (EVID / "sitemap_recon.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
