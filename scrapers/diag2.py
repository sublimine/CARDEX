"""Diagnostic 2 — AS24 URL discovery + mobile.de curl_cffi."""
import asyncio, re, sys
from curl_cffi.requests import AsyncSession

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

AS24_URLS = [
    "https://www.autoscout24.de/lst?atype=C&cy=D&desc=0&sort=standard",
    "https://www.autoscout24.de/lst/?atype=C",
    "https://www.autoscout24.de/lst",
    "https://www.autoscout24.de/",
]

MOBILE_URL = "https://suchen.mobile.de/fahrzeuge/search.html?isSearchRequest=true&pageSize=20&pageNumber=1"
KLEINANZEIGEN_URL = "https://www.kleinanzeigen.de/s-autos/seite:1/c216"
MARKTPLAATS_API = "https://www.marktplaats.nl/lrp/api/search?l1CategoryId=91&offset=0&limit=30&searchInTitleAndDescription=true"


def show(name, url, r):
    text = r.text
    print(f"\n{'='*60}\n{name} | HTTP {r.status_code} | {len(text)} chars")
    title = re.search(r'<title[^>]*>([^<]{0,80})', text, re.I)
    print(f"TITLE: {title.group(1) if title else 'n/a'}")
    # Find all hrefs containing autoscout24 listing paths
    hrefs = re.findall(r'href="([^"]{0,200})"', text)
    listing_hrefs = [h for h in hrefs if any(x in h for x in ['angebote','annonces','anuncios','aanbod'])]
    print(f"LISTING HREFS ({len(listing_hrefs)}): {listing_hrefs[:5]}")
    # Find absolute listing URLs
    abs_urls = re.findall(r'https?://[^\s"\'<>]{10,}(?:angebote|annonces|anuncios|aanbod)[^\s"\'<>]{3,}', text)
    abs_urls_dedup = list(dict.fromkeys(abs_urls))[:5]
    print(f"ABS LISTING URLS ({len(abs_urls)}): {abs_urls_dedup}")
    # Show first 400 chars
    snippet = text[:400].replace('\n', ' ').replace('\r', '')
    print(f"HTML: {snippet}")


async def main():
    async with AsyncSession() as sess:
        # AS24 — try multiple URLs
        for url in AS24_URLS:
            try:
                r = await sess.get(url, impersonate="chrome124", timeout=15, allow_redirects=True)
                show(f"AS24_DE {url[-40:]}", url, r)
                # If we find listing URLs, stop
                text = r.text
                hits = re.findall(r'autoscout24\.de/(?:angebote|lst)[^\s"\'<>]+', text)
                if hits:
                    print(f"** FOUND {len(hits)} potential listing refs **")
                    break
            except Exception as e:
                print(f"AS24 {url}: ERROR {e}")
            await asyncio.sleep(1)

        # mobile.de with curl_cffi
        print(f"\n{'='*60}\nMOBILE_DE with curl_cffi")
        try:
            r = await sess.get(MOBILE_URL, impersonate="chrome124", timeout=15)
            text = r.text
            print(f"HTTP {r.status_code} | {len(text)} chars")
            title = re.search(r'<title[^>]*>([^<]{0,80})', text, re.I)
            print(f"TITLE: {title.group(1) if title else 'n/a'}")
            hits = re.findall(r'(?:mobile\.de/fahrzeuge/details[^\s"\'<>]+|id=\d{7,})', text)
            print(f"LISTING HITS: {list(dict.fromkeys(hits))[:5]}")
        except Exception as e:
            print(f"mobile.de ERROR: {e}")

        # kleinanzeigen — check actual pattern
        print(f"\n{'='*60}\nKLEINANZEIGEN pattern check")
        try:
            r = await sess.get(KLEINANZEIGEN_URL, impersonate="chrome124", timeout=15)
            text = r.text
            print(f"HTTP {r.status_code} | {len(text)} chars")
            hits = re.findall(r'/s-anzeige/[^"\'&?\s<>]+', text)
            hits_dedup = list(dict.fromkeys(hits))[:8]
            print(f"HITS ({len(hits)}): {hits_dedup}")
        except Exception as e:
            print(f"kleinanzeigen ERROR: {e}")

        # marktplaats JSON API
        print(f"\n{'='*60}\nMARKTPLAATS JSON API")
        try:
            r = await sess.get(MARKTPLAATS_API, impersonate="chrome124", timeout=15,
                               headers={"Accept": "application/json"})
            print(f"HTTP {r.status_code} | {len(r.text)} chars")
            import json
            data = json.loads(r.text)
            listings = data.get('listings', [])
            print(f"Listings in response: {len(listings)}")
            if listings:
                print(f"Sample URL: {listings[0].get('vipUrl','') or listings[0]}")
        except Exception as e:
            print(f"marktplaats ERROR: {e}")

    print("\nDONE")


asyncio.run(main())
