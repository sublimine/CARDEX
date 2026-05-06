"""Diag corrected URLs — find real listing patterns."""
import asyncio, re
from curl_cffi.requests import AsyncSession
import httpx

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def find_listings(text, hints, name):
    results = {}
    for pattern, label in hints:
        hits = list(dict.fromkeys(re.findall(pattern, text, re.I)))[:5]
        if hits:
            results[label] = hits
            print(f"  [{label}] ({len(re.findall(pattern, text, re.I))} hits): {hits[:4]}")
    if not results:
        print(f"  NO PATTERNS MATCHED for {name}")
        # Fallback: show all long hrefs
        hrefs = [h for h in re.findall(r'href=["\']([^"\']{20,})["\']', text)
                 if not any(x in h for x in ['.css','.js','.png','.svg','#','javascript:'])]
        print(f"  Long hrefs sample: {list(dict.fromkeys(hrefs))[:5]}")


async def main():
    async with AsyncSession() as sess:
        async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=20,
                                      follow_redirects=True, http2=True) as hx:

            # coches.net — correct pagination URL
            print("=== COCHES.NET (corrected) ===")
            r = await sess.get(
                "https://www.coches.net/segunda-mano/?Section1Id=2500&pg=1",
                impersonate="chrome124", timeout=20
            )
            print(f"HTTP {r.status_code} | {len(r.text):,}")
            find_listings(r.text, [
                (r'href="(/segunda-mano/[^"?&]{20,})"', "relative listing href"),
                (r'"(/segunda-mano/[a-z0-9-]+/[a-z0-9-]+-\d+\.html)"', "JSON listing path"),
                (r'coches\.net/segunda-mano/[a-z0-9-]+/[a-z0-9-]+-\d+', "absolute listing"),
            ], "coches.net")
            await asyncio.sleep(1.5)

            # autocasion.es — correct param is p=
            print("\n=== AUTOCASION (corrected) ===")
            r = await hx.get("https://www.autocasion.com/coches-segunda-mano/?p=1")
            print(f"HTTP {r.status_code} | {len(r.text):,}")
            find_listings(r.text, [
                (r'href="(/coche/[^"]{10,})"', "relative listing href"),
                (r'autocasion\.com/coche/[^"\'&?\s<>]+', "absolute listing"),
                (r'"(/coche/[^"]{10,})"', "JSON listing path"),
            ], "autocasion")
            await asyncio.sleep(1.5)

            # coches.com — correct path /coches-segunda-mano/
            print("\n=== COCHES.COM (corrected) ===")
            r = await hx.get("https://www.coches.com/coches-segunda-mano/?page=1")
            print(f"HTTP {r.status_code} | {len(r.text):,}")
            find_listings(r.text, [
                (r'href="(/coches-segunda-mano/[^"]{15,})"', "relative listing href"),
                (r'"(/coches-segunda-mano/[^"]{15,})"', "JSON listing"),
                (r'coches\.com/coches-segunda-mano/[^"\'&?\s<>]+', "absolute"),
            ], "coches.com")
            await asyncio.sleep(1.5)

            # autohero.com — correct path /de/search/
            print("\n=== AUTOHERO (corrected) ===")
            r = await sess.get("https://www.autohero.com/de/search/?page=1",
                               impersonate="chrome124", timeout=20)
            print(f"HTTP {r.status_code} | {len(r.text):,}")
            find_listings(r.text, [
                (r'href="(/de/auto/[^"]{10,})"', "relative listing href"),
                (r'"(/de/auto/[^"]{10,})"', "JSON listing"),
                (r'autohero\.com/de/auto/[^"\'&?\s<>]+', "absolute"),
            ], "autohero")
            await asyncio.sleep(1.5)

            # heycar — German site
            print("\n=== HEYCAR (German) ===")
            for url in ["https://heycar.com/de/autos", "https://www.heycar.de/",
                        "https://heycar.com/de/gebrauchtwagen"]:
                try:
                    r = await sess.get(url, impersonate="chrome124", timeout=15)
                    print(f"  {url[-40:]} -> HTTP {r.status_code} | {len(r.text):,}")
                    if r.status_code == 200 and len(r.text) > 10000:
                        hits = re.findall(r'href="(/de/auto/[^"]{10,})"', r.text)
                        hits2 = re.findall(r'"(/de/auto/[^"]{10,})"', r.text)
                        print(f"    /de/auto/ hrefs: {len(hits)} | JSON: {len(hits2)}")
                        print(f"    examples: {list(dict.fromkeys(hits+hits2))[:3]}")
                except Exception as e:
                    print(f"  {url}: ERROR {e}")
                await asyncio.sleep(1)

            # pkw.de — find correct listing URL
            print("\n=== PKW.DE ===")
            r = await hx.get("https://www.pkw.de/")
            print(f"HTTP {r.status_code} | {len(r.text):,}")
            # Find links to gebrauchtwagen
            gbw = [h for h in re.findall(r'href=["\']([^"\']+)["\']', r.text)
                   if 'gebraucht' in h.lower() or '/autos/' in h]
            print(f"  gebrauchtwagen links: {gbw[:5]}")
            await asyncio.sleep(1)

            # mobile.de — check for accessible URLs
            print("\n=== MOBILE.DE — sitemap/RSS check ===")
            for url in [
                "https://www.mobile.de/sitemap.xml",
                "https://suchen.mobile.de/fahrzeuge/search.html?categories=CAR&pageNumber=1",
                "https://m.mobile.de/fahrzeuge/search.html?pageNumber=1",
            ]:
                try:
                    r2 = await sess.get(url, impersonate="chrome124", timeout=15)
                    title = re.search(r'<title[^>]*>([^<]{0,60})', r2.text, re.I)
                    t = title.group(1) if title else "n/a"
                    print(f"  {url[-50:]} -> {r2.status_code} | {len(r2.text):,} | {t}")
                    if r2.status_code == 200 and ('mobile.de' in r2.text or 'fahrzeug' in r2.text.lower()):
                        hits = re.findall(r'https://suchen\.mobile\.de/fahrzeuge/details[^"\'<>\s]+', r2.text)
                        print(f"    listing URLs: {list(dict.fromkeys(hits))[:3]}")
                except Exception as e:
                    print(f"  ERROR: {e}")
                await asyncio.sleep(1)

    print("\nDONE")


asyncio.run(main())
