"""
Find JSON APIs for DPG Media portals (autotrack, gaspedaal) and mobile.de.
DPG Media WAF blocks IPs but may have accessible API endpoints.
"""
import asyncio, re
from curl_cffi.requests import AsyncSession

TESTS = [
    # autotrack.nl JSON APIs
    ("autotrack_api1", "https://www.autotrack.nl/api/search?categoryId=1&page=1"),
    ("autotrack_api2", "https://www.autotrack.nl/api/occasions?page=1"),
    ("autotrack_api3", "https://www.autotrack.nl/api/v1/vehicles?page=1&type=personal"),
    ("autotrack_sitemap", "https://www.autotrack.nl/sitemap.xml"),
    ("autotrack_robots", "https://www.autotrack.nl/robots.txt"),
    # gaspedaal
    ("gaspedaal_api1", "https://www.gaspedaal.nl/api/search?page=1"),
    ("gaspedaal_robots", "https://www.gaspedaal.nl/robots.txt"),
    ("gaspedaal_sitemap", "https://www.gaspedaal.nl/sitemap.xml"),
    # mobile.de
    ("mobile_sitemap_index", "https://www.mobile.de/sitemap-index.xml"),
    ("mobile_rss", "https://suchen.mobile.de/fahrzeuge/rss?categories=CAR&pageNumber=1"),
    ("mobile_api", "https://suchen.mobile.de/api/search-service/search?categories=CAR&pageNumber=1&pageSize=20"),
    ("mobile_gebrauchtwagen_xml", "https://www.mobile.de/sitemap-used-car-1.xml"),
    # lacentrale — try direct API
    ("lacentrale_api", "https://www.lacentrale.fr/api/v1/ad/search?page=1"),
    ("lacentrale_robots", "https://www.lacentrale.fr/robots.txt"),
    # leboncoin
    ("leboncoin_api", "https://api.leboncoin.fr/api/adfinder/v1/search"),
    ("leboncoin_robots", "https://www.leboncoin.fr/robots.txt"),
]

async def main():
    async with AsyncSession() as sess:
        for name, url in TESTS:
            try:
                r = await sess.get(url, impersonate="chrome124", timeout=10,
                                   headers={"Accept": "application/json,text/html,*/*"})
                preview = r.text[:200].replace('\n', ' ')
                print(f"{name} -> HTTP {r.status_code} | {len(r.text):,} | {preview[:150]}")
            except Exception as e:
                print(f"{name} -> ERROR {e}")
            await asyncio.sleep(0.5)
    print("DONE")

asyncio.run(main())
