#!/usr/bin/env python3
"""Hard-evidence test of the coches.net KEYLESS private JSON API.

Source (market research): POST https://ms-mt--api-web.spain.advgo.net/search/listing
with x-schibsted-tenant: coches and no auth. If it returns listings, this is a
cost-zero, browser-free path to the entire Spanish used-car inventory.

Evidence-first: prints HTTP status, payload size, listing count, and a sample of
real extracted fields. Tries several curl_cffi impersonations and a fallback
barer payload. No verdict without the actual response.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from curl_cffi import requests as cr

EVID = Path(__file__).resolve().parent / "evidence"
EVID.mkdir(parents=True, exist_ok=True)

API = "https://ms-mt--api-web.spain.advgo.net/search/listing"

HEADERS = {
    "content-type": "application/json;charset=UTF-8",
    "accept": "application/json;charset=UTF-8",
    "origin": "https://www.coches.net",
    "referer": "https://www.coches.net/",
    "x-adevinta-channel": "web-desktop",
    "x-schibsted-tenant": "coches",
    "accept-language": "es-ES,es;q=0.9",
}

BODY = {
    "pagination": {"page": 0, "size": 100},
    "sort": {"order": "desc", "term": "relevance"},
    "filters": {
        "categories": {"category1Ids": [2500]},
        "offerTypeIds": [0, 2, 3, 4, 5],
        "contractId": 0,
        "sellerTypeId": 0,
        "transmissionTypeId": 0,
        "price": {"from": None, "to": None},
        "year": {"from": None, "to": None},
        "km": {"from": None, "to": None},
        "provinceIds": [],
    },
}


def summarize(js: dict) -> tuple[int, list]:
    """coches API returns {'items':[...], 'meta':{...}} or similar. Find the list."""
    items = None
    for key in ("items", "results", "listings", "ads", "data"):
        if isinstance(js.get(key), list):
            items = js[key]
            break
    if items is None:
        # search one level deep
        for v in js.values():
            if isinstance(v, dict):
                for key in ("items", "results", "listings", "ads"):
                    if isinstance(v.get(key), list):
                        items = v[key]
                        break
    total = None
    for key in ("totalResults", "total", "count", "totalHits"):
        if isinstance(js.get(key), (int, float)):
            total = int(js[key])
        elif isinstance(js.get("meta"), dict) and isinstance(js["meta"].get(key), (int, float)):
            total = int(js["meta"][key])
    return total, (items or [])


def attempt(label: str, impersonate: str, body: dict, proxy: str | None = None) -> bool:
    print(f"\n--- attempt: {label} (impersonate={impersonate}, proxy={proxy}) ---")
    t0 = time.time()
    try:
        kwargs = dict(headers=HEADERS, json=body, impersonate=impersonate, timeout=30)
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}
        r = cr.post(API, **kwargs)
    except Exception as e:
        print(f"  EXC after {time.time()-t0:.1f}s: {e}")
        return False
    print(f"  HTTP_STATUS={r.status_code}  bytes={len(r.content)}  elapsed={time.time()-t0:.1f}s")
    ctype = r.headers.get("content-type", "")
    print(f"  content-type={ctype}")
    if r.status_code != 200:
        print(f"  body_head={r.text[:300]!r}")
        return False
    try:
        js = r.json()
    except Exception:
        print(f"  NOT JSON. body_head={r.text[:300]!r}")
        return False
    total, items = summarize(js)
    print(f"  TOTAL_RESULTS={total}  items_in_page={len(items)}")
    if items:
        out = EVID / "coches_api_sample.json"
        out.write_text(json.dumps(items[:3], indent=2, ensure_ascii=False), encoding="utf-8")
        sample = items[0]
        keys = list(sample.keys()) if isinstance(sample, dict) else type(sample)
        print(f"  SAMPLE_KEYS={keys}")
        # try to surface human-readable fields
        if isinstance(sample, dict):
            for k in ("title", "id", "price", "year", "km", "kms", "url", "make", "model"):
                if k in sample:
                    print(f"    {k}={sample[k]!r}")
        print(f"  WROTE sample -> {out}")
        full = EVID / "coches_api_full_page.json"
        full.write_text(json.dumps(js, ensure_ascii=False)[:500000], encoding="utf-8")
        print(f"  WROTE full page -> {full}")
        return True
    print(f"  json_head={json.dumps(js, ensure_ascii=False)[:300]}")
    return False


def main() -> int:
    # Attempt matrix: different TLS fingerprints; then a barer payload.
    impersonations = ["chrome131", "chrome124", "chrome120", "safari17_0", "firefox133"]
    for imp in impersonations:
        if attempt(f"full-body {imp}", imp, BODY):
            print("\nRESULT: SUCCESS — coches.net keyless API returned real listings.")
            return 0

    barer = {"pagination": {"page": 0, "size": 50}, "filters": {"categories": {"category1Ids": [2500]}}}
    for imp in ["chrome131", "safari17_0"]:
        if attempt(f"bare-body {imp}", imp, barer):
            print("\nRESULT: SUCCESS (bare body) — coches.net keyless API returned real listings.")
            return 0

    print("\nRESULT: no 200+listings yet from this IP. See statuses above for next step.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
