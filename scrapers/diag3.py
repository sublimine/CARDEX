"""Diag3 — AS24 JSON extraction + mobile.de alternatives."""
import asyncio, re, json
from curl_cffi.requests import AsyncSession
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    async with AsyncSession() as sess:
        # AS24 — find listing URLs in Next.js JSON
        print("=== AS24 JSON EXTRACTION ===")
        r = await sess.get(
            "https://www.autoscout24.de/lst?atype=C&cy=D&desc=0&sort=standard",
            impersonate="chrome124", timeout=20,
        )
        text = r.text

        # Try __NUXT_DATA__ or __NEXT_DATA__
        for marker in ['__NUXT_DATA__', '__NEXT_DATA__', '__INITIAL_STATE__']:
            m = re.search(rf'<script[^>]*id="{marker}"[^>]*>(.*?)</script>', text, re.DOTALL)
            if m:
                print(f"Found {marker}, length={len(m.group(1))}")
                raw = m.group(1)[:3000]
                # Look for /angebote/ paths in JSON
                angebote = re.findall(r'/angebote/[^"\'\\]+', raw)
                print(f"  /angebote/ refs in JSON: {angebote[:5]}")
                break
        else:
            print("No known JSON marker found")

        # Look for /angebote/ anywhere in page
        all_angebote = re.findall(r'(?:href=|"url":|"link":)"?(/angebote/[^"\'&?\s<>]+)', text)
        print(f"All /angebote/ refs: {len(all_angebote)}, examples: {list(dict.fromkeys(all_angebote))[:5]}")

        # Look in window.__STORE__ or inline scripts
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', text, re.DOTALL)
        print(f"Total <script> blocks: {len(scripts)}")
        for i, sc in enumerate(scripts):
            refs = re.findall(r'/angebote/[^"\'\\]+', sc)
            if refs:
                print(f"  Script[{i}] has {len(refs)} /angebote/ refs: {refs[:3]}")

        # Check if there's a data- attribute with listing JSON
        data_attrs = re.findall(r'data-(?:listing|vehicle|ad)-id="([^"]+)"', text)
        print(f"data-*-id attrs: {data_attrs[:5]}")

        # Look for listing URLs in ANY format
        all_hrefs = re.findall(r'href="(/[^"]{5,})"', text)
        listing_hrefs = [h for h in all_hrefs if '/angebote/' in h or '/lst/' in h]
        print(f"Listing hrefs (relative): {listing_hrefs[:5]}")

        print("\n=== MOBILE.DE alternatives ===")
        for url in [
            "https://www.mobile.de/sitemap-used-car-1.xml",
            "https://suchen.mobile.de/fahrzeuge/search.html?categories=CAR&pageNumber=1&pageSize=20",
            "https://www.mobile.de/",
        ]:
            try:
                r2 = await sess.get(url, impersonate="chrome124", timeout=15)
                print(f"  {url[-50:]} -> HTTP {r2.status_code} | {len(r2.text)} chars")
                if r2.status_code == 200:
                    hits = re.findall(r'(?:id=|/fahrzeuge/details\.html\?id=)\d{7,}', r2.text)
                    print(f"    listing refs: {len(hits)}, ex: {hits[:3]}")
            except Exception as e:
                print(f"  {url}: ERROR {e}")
            await asyncio.sleep(1)

    print("\nDONE")

asyncio.run(main())
