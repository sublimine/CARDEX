"""
Comprehensive portal diagnostic — tests every portal that returned 0 URLs.
Runs sequentially to avoid CF cross-detection.
Shows: HTTP status, page title, and the actual URL patterns present.
"""
import asyncio, re, json
from curl_cffi.requests import AsyncSession
import httpx

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

PORTALS = [
    # (name, client, url, hint_patterns)
    ("heycar_de",       "curl", "https://hey.car/gebrauchtwagen?page=1",
     [r'hey\.car/[a-z0-9-]+/[a-z0-9-]+/[A-Za-z0-9]{8,}', r'href="(/[^"]{20,})"']),
    ("pkw_de",          "httpx","https://www.pkw.de/gebrauchtwagensuche.html?page=1",
     [r'pkw\.de/autos/[^"\']+\.html', r'href="(/autos/[^"\']+\.html)"']),
    ("automobile_de",   "httpx","https://www.automobile.de/gebrauchtwagen/?page=1&sort=date_desc",
     [r'automobile\.de/auto-\d+\.html', r'href="(/auto-\d+\.html)"']),
    ("autohero_de",     "curl", "https://www.autohero.com/de/gebrauchtwagen/?page=1",
     [r'autohero\.com/de/auto/[^"\']+', r'href="(/de/auto/[^"\']+)"']),
    ("coches_net",      "curl", "https://www.coches.net/segunda-mano/?pag=1",
     [r'coches\.net/segunda-mano/[^"\'&?]+', r'href="(/segunda-mano/[^"\'&?]+)"']),
    ("milanuncios",     "curl", "https://www.milanuncios.com/coches-de-segunda-mano/?pag=1",
     [r'milanuncios\.com/coches-de-segunda-mano/[^"\']+\.htm', r'href="(/coches-de-segunda-mano/[^"\']+\.htm)"']),
    ("autocasion",      "httpx","https://www.autocasion.com/coches-segunda-mano/page/1/",
     [r'autocasion\.com/coche/[^"\']+', r'href="(/coche/[^"\']+)"']),
    ("motor_es",        "httpx","https://www.motor.es/coches/segunda-mano/todos-los-modelos/?pag=1",
     [r'motor\.es/coches/segunda-mano/[^"\'&?]+-\d+', r'href="(/coches/segunda-mano/[^"\'&?]+-\d+)"']),
    ("coches_com",      "curl", "https://www.coches.com/segunda-mano/?page=1",
     [r'coches\.com/segunda-mano/[^"\'&?/]+/[^"\'&?]+', r'href="(/segunda-mano/[^"\'&?/]+/[^"\'&?]+)"']),
    ("flexicar",        "httpx","https://www.flexicar.es/coches-segunda-mano?page=1",
     [r'flexicar\.es/coches-segunda-mano/[^"\'&?]+', r'href="(/coches-segunda-mano/[^"\'&?]+)"']),
    ("leboncoin",       "curl", "https://www.leboncoin.fr/recherche?category=2&page=1",
     [r'leboncoin\.fr/voitures/\d+\.htm', r'"/voitures/\d+\.htm"']),
    ("lacentrale",      "curl", "https://www.lacentrale.fr/listing?page=1",
     [r'lacentrale\.fr/auto-occasion-annonce-\d+\.html', r'href="(/auto-occasion-annonce-\d+\.html)"']),
    ("paruvendu",       "httpx","https://www.paruvendu.fr/auto/annonceauto/liste/?p=1&tt=1",
     [r'paruvendu\.fr/auto/annonceauto/detail/\d+/', r'href="(/auto/annonceauto/detail/\d+/)"']),
    ("largus_fr",       "httpx","https://www.largus.fr/voitures-occasion/page-1.html",
     [r'largus\.fr/voiture-occasion-[^"\']+\d+\.html', r'href="(/voiture-occasion-[^"\']+\d+\.html)"']),
    ("caradisiac",      "httpx","https://www.caradisiac.com/occasion/?page=1",
     [r'caradisiac\.com/occasion/[^"\'&?]+-\d+\.htm', r'href="(/occasion/[^"\'&?]+-\d+\.htm)"']),
    ("ouestfrance",     "httpx","https://www.ouestfrance-auto.com/auto/?page=1",
     [r'ouestfrance-auto\.com/auto/voiture/[^"\'&?]+/\d+/', r'href="(/auto/voiture/[^"\'&?]+/\d+/)"']),
    ("autotrack_nl",    "httpx","https://www.autotrack.nl/occasion/personen?page=1",
     [r'autotrack\.nl/autos/[^"\'&?]+/\d+/', r'href="(/autos/[^"\'&?]+/\d+/)"']),
    ("gaspedaal_nl",    "httpx","https://www.gaspedaal.nl/occasion?page=1",
     [r'gaspedaal\.nl/[^"\'&?/]+/[^"\'&?/]+/[^"\'&?]+-\d+', r'href="(/[a-z][^"\'&?/]+/[^"\'&?/]+/[^"\'&?]+-\d+)"']),
    ("gocar_be",        "httpx","https://www.gocar.be/voitures-occasions?page=1",
     [r'gocar\.be/voiture-occasion/[^"\'&?]+', r'href="(/voiture-occasion/[^"\'&?]+)"']),
    ("comparis_ch",     "httpx","https://www.comparis.ch/carfinder/markt/result.aspx?page=1",
     [r'comparis\.ch/carfinder/markt/details\.aspx\?id=\d+', r'href="(/carfinder/markt/details\.aspx\?id=\d+)"']),
]


def analyse(name, status, text, patterns):
    title = (re.search(r'<title[^>]*>([^<]{0,80})', text, re.I) or type('', (), {'group': lambda s, n: 'n/a'})()).group(1)
    print(f"\n{'='*60}")
    print(f"{name} | HTTP {status} | {len(text):,} chars")
    print(f"TITLE: {title}")
    if status != 200:
        print(f"BLOCKED: {text[:200]}")
        return
    for pat in patterns:
        hits = list(dict.fromkeys(re.findall(pat, text, re.I)))[:4]
        print(f"  [{pat[:55]}] → {len(re.findall(pat, text, re.I))} hits: {hits}")


async def main():
    async with AsyncSession() as curl_sess:
        async with httpx.AsyncClient(
            headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.8",
                     "Accept-Language": "de-DE,de;q=0.9,fr;q=0.8,nl;q=0.7,es;q=0.6"},
            timeout=20, follow_redirects=True, http2=True,
        ) as hx:
            for name, client, url, patterns in PORTALS:
                try:
                    if client == "curl":
                        r = await curl_sess.get(url, impersonate="chrome124", timeout=20)
                        status, text = r.status_code, r.text
                    else:
                        r = await hx.get(url)
                        status, text = r.status_code, r.text
                    analyse(name, status, text, patterns)
                except Exception as e:
                    print(f"\n{name}: ERROR {e}")
                await asyncio.sleep(1.5)

    print("\n\nDONE")


asyncio.run(main())
