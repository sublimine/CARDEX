"""
Live diagnostic — qué devuelven realmente AS24 y otros portales.
Ejecutar: py -m scrapers.diag desde CARDEX/
"""
import asyncio, re, sys
from curl_cffi.requests import AsyncSession
import httpx

TESTS = [
    {
        "name": "AS24_DE",
        "client": "curl",
        "url": "https://www.autoscout24.de/lst/gebrauchtwagen?atype=C&page=1",
        "patterns": [
            r'autoscout24\.de/angebote/[^"\'&?\s<>]+\.html',
            r'autoscout24\.de/angebote/[^"\'&?\s<>]+',
            r'/angebote/[^"\'&?\s<>]+',
            r'"url"\s*:\s*"[^"]*angebote[^"]*"',
            r'href="[^"]*autoscout24[^"]*"',
        ],
    },
    {
        "name": "MOBILE_DE",
        "client": "httpx",
        "url": "https://suchen.mobile.de/fahrzeuge/search.html?isSearchRequest=true&pageSize=20&pageNumber=1",
        "patterns": [
            r'suchen\.mobile\.de/fahrzeuge/details\.html\?id=\d+',
            r'details\.html\?id=\d+',
            r'mobile\.de/fahrzeuge[^"\'&?\s<>]+',
        ],
    },
    {
        "name": "KLEINANZEIGEN",
        "client": "httpx",
        "url": "https://www.kleinanzeigen.de/s-autos/seite:1/c216",
        "patterns": [
            r'kleinanzeigen\.de/s-anzeige/[^"\'&?\s<>]+',
            r'/s-anzeige/[^"\'&?\s<>]+',
            r'href="/s-anzeige[^"]*"',
        ],
    },
    {
        "name": "COCHES_NET",
        "client": "curl",
        "url": "https://www.coches.net/segunda-mano/?pag=1&por-pagina=10",
        "patterns": [
            r'coches\.net/segunda-mano/[^"\'&?\s<>]+-\d+\.html',
            r'/segunda-mano/[^"\'&?\s<>]+-\d+\.html',
            r'href="[^"]*segunda-mano[^"]*"',
        ],
    },
    {
        "name": "LACENTRALE",
        "client": "curl",
        "url": "https://www.lacentrale.fr/listing?makesModelsCommercialNames=&page=1",
        "patterns": [
            r'lacentrale\.fr/auto-occasion-annonce-\d+\.html',
            r'/auto-occasion-annonce-\d+\.html',
            r'href="[^"]*auto-occasion[^"]*"',
        ],
    },
]

HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}


async def test_one(test: dict) -> None:
    name = test["name"]
    url = test["url"]
    print(f"\n{'='*60}")
    print(f"SOURCE: {name}")
    print(f"URL: {url}")

    try:
        if test["client"] == "curl":
            async with AsyncSession() as sess:
                r = await sess.get(url, impersonate="chrome124", timeout=20)
        else:
            async with httpx.AsyncClient(headers=HDR, timeout=20, follow_redirects=True, http2=True) as cl:
                r = await cl.get(url)

        print(f"HTTP: {r.status_code} | len={len(r.text)}")
        print(f"TITLE: {re.search(r'<title[^>]*>([^<]+)</title>', r.text, re.I) and re.search(r'<title[^>]*>([^<]+)</title>', r.text, re.I).group(1) or 'not found'}")
        print(f"HTML[0:300]: {r.text[:300].replace(chr(10),' ')}")
        print()

        for pat in test["patterns"]:
            hits = re.findall(pat, r.text, re.I)
            hits_dedup = list(dict.fromkeys(hits))[:5]
            print(f"  PATTERN [{pat[:60]}]")
            print(f"  → {len(hits)} hits | examples: {hits_dedup}")

    except Exception as exc:
        print(f"ERROR: {exc}")


async def main():
    for t in TESTS:
        await test_one(t)
    print("\n" + "="*60)
    print("DONE")


if __name__ == "__main__":
    asyncio.run(main())
