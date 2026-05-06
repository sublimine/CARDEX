"""
Diag7 — AS24 DE isolated run: 3 segments, 2 pages each.
Tests if AS24 works in isolation (no parallel scrapers).
"""
import asyncio, re
from curl_cffi.requests import AsyncSession
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BASE = "https://www.autoscout24.de/lst"
RE = re.compile(r'"(/angebote/[^"\\]{20,})"', re.I)
SLEEP = 1.5

async def fetch(sess, url):
    r = await sess.get(url, impersonate="chrome124", timeout=20)
    hits = list(dict.fromkeys(RE.findall(r.text)))
    print(f"  HTTP {r.status_code} | {len(r.text)} chars | listings: {len(hits)}")
    if hits:
        print(f"  sample: {hits[0][:80]}")
    return hits

async def main():
    segments = [
        (2020, 2022, 30000, ""),
        (2018, 2020, 20000, "D"),
        (2015, 2018, 10000, "P"),
    ]
    async with AsyncSession() as sess:
        for (yf, yt, pt, fuel) in segments:
            for page in [1, 2]:
                url = f"{BASE}?atype=C&desc=0&sort=standard&year_from={yf}&year_to={yt}&price_to={pt}&page={page}"
                if fuel:
                    url += f"&fuel={fuel}"
                print(f"\nsegment year={yf}-{yt} price_to={pt} fuel={fuel or 'all'} page={page}")
                hits = await fetch(sess, url)
                await asyncio.sleep(SLEEP)
                if not hits:
                    print("  -> ZERO results, stopping segment")
                    break

asyncio.run(main())
