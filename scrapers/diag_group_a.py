"""Diag Group A — extract real URL patterns from working portals."""
import asyncio, re
from curl_cffi.requests import AsyncSession
import httpx

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def find_listing_urls(name, text, domain_hint):
    """Find all hrefs containing likely listing paths."""
    # All hrefs
    all_hrefs = re.findall(r'href=["\']([^"\']{10,})["\']', text)
    # Filter: must contain domain or be relative, and have meaningful path
    results = []
    for h in all_hrefs:
        if domain_hint in h or (h.startswith('/') and len(h) > 15):
            # Exclude obvious non-listing paths
            if not any(x in h for x in ['.css','.js','.png','.jpg','.svg','/static/','/assets/',
                                          'javascript:','mailto:','#','/search','/sitemap',
                                          '/account','/login','/register','/help']):
                results.append(h)
    results = list(dict.fromkeys(results))
    print(f"  Listing-like hrefs ({len(results)}): {results[:8]}")
    # Also look for JSON "url" patterns
    json_urls = re.findall(r'"(?:url|href|link|path)"\s*:\s*"(/[^"]{10,})"', text)
    json_urls = list(dict.fromkeys(json_urls))[:5]
    if json_urls:
        print(f"  JSON url fields: {json_urls}")


async def main():
    async with AsyncSession() as sess:
        async with httpx.AsyncClient(
            headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.8"},
            timeout=20, follow_redirects=True, http2=True
        ) as hx:

            # heycar.de — UK redirect! Need .de domain
            print("=== HEYCAR ===")
            r = await sess.get("https://hey.car/gebrauchtwagen?page=1", impersonate="chrome124", timeout=20)
            print(f"URL: {r.url} | HTTP {r.status_code} | {len(r.text)} chars")
            find_listing_urls("heycar", r.text, "hey.car")
            await asyncio.sleep(1)

            # coches.net
            print("\n=== COCHES.NET ===")
            r = await sess.get("https://www.coches.net/segunda-mano/?pag=1", impersonate="chrome124", timeout=20)
            print(f"HTTP {r.status_code} | {len(r.text)} chars")
            find_listing_urls("coches.net", r.text, "coches.net")
            # Also check what the JSON data says
            json_patterns = re.findall(r'"/segunda-mano/[^"]{10,}"', r.text)[:5]
            print(f"  /segunda-mano/ in JSON: {json_patterns}")
            await asyncio.sleep(1)

            # flexicar.es
            print("\n=== FLEXICAR ===")
            r = await hx.get("https://www.flexicar.es/coches-segunda-mano?page=1")
            print(f"HTTP {r.status_code} | {len(r.text)} chars")
            find_listing_urls("flexicar", r.text, "flexicar.es")
            await asyncio.sleep(1)

            # ouestfrance — 212 chars suggests redirect
            print("\n=== OUESTFRANCE ===")
            r = await hx.get("https://www.ouestfrance-auto.com/auto/?page=1")
            print(f"HTTP {r.status_code} | {len(r.text)} chars | URL: {r.url}")
            print(f"Content: {r.text[:300]}")
            await asyncio.sleep(1)

            # Find correct 404 portal URLs
            print("\n=== FINDING CORRECT URLs FOR 404 PORTALS ===")

            for name, urls in [
                ("pkw.de", [
                    "https://www.pkw.de/gebrauchtwagen/",
                    "https://www.pkw.de/auto/?page=1",
                    "https://www.pkw.de/",
                ]),
                ("automobile.de", [
                    "https://www.automobile.de/",
                    "https://www.automobile.de/gebrauchtwagen",
                    "https://www.automobile.de/s/gebrauchtwagen/?page=1",
                ]),
                ("autohero.com", [
                    "https://www.autohero.com/de/",
                    "https://www.autohero.com/de/search/",
                    "https://www.autohero.com/de/buy/?page=1",
                ]),
                ("autocasion.com", [
                    "https://www.autocasion.com/coches-segunda-mano/",
                    "https://www.autocasion.com/",
                    "https://www.autocasion.com/coches-segunda-mano/?p=1",
                ]),
                ("coches.com", [
                    "https://www.coches.com/segunda-mano/",
                    "https://www.coches.com/",
                    "https://www.coches.com/coches-segunda-mano/?page=1",
                ]),
                ("paruvendu.fr", [
                    "https://www.paruvendu.fr/auto/",
                    "https://www.paruvendu.fr/auto/voiture/",
                    "https://www.paruvendu.fr/auto/?p=1",
                ]),
                ("comparis.ch", [
                    "https://www.comparis.ch/carfinder/",
                    "https://www.comparis.ch/carfinder/markt/",
                    "https://www.comparis.ch/auto/",
                ]),
            ]:
                print(f"\n  [{name}]")
                for url in urls:
                    try:
                        if ".de" in url or ".com" in url or ".es" in url or ".fr" in url or ".ch" in url:
                            r2 = await hx.get(url)
                        else:
                            r2 = await hx.get(url)
                        title = re.search(r'<title[^>]*>([^<]{0,60})', r2.text, re.I)
                        t = title.group(1) if title else "n/a"
                        print(f"    {url[-50:]} -> {r2.status_code} | {len(r2.text):,} | {t}")
                    except Exception as e:
                        print(f"    {url[-50:]} -> ERROR {e}")
                    await asyncio.sleep(0.5)

    print("\nDONE")


asyncio.run(main())
