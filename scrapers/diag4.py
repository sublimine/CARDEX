"""Smoke test AS24 fix + kleinanzeigen fix."""
import asyncio, re
from curl_cffi.requests import AsyncSession
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    async with AsyncSession() as sess:
        # AS24 DE — 1 page
        print("=== AS24 DE smoke test ===")
        r = await sess.get(
            "https://www.autoscout24.de/lst?atype=C&desc=0&sort=standard&year_from=2020&year_to=2022&price_to=30000&page=1",
            impersonate="chrome124", timeout=20
        )
        rel_re = re.compile(r'href="(/angebote/[a-z0-9][^"\'&?\s<>]{20,})"', re.I)
        hits = list(dict.fromkeys(rel_re.findall(r.text)))
        print(f"HTTP {r.status_code} | {len(r.text)} chars | listing hrefs: {len(hits)}")
        for h in hits[:5]:
            print(f"  https://www.autoscout24.de{h}")

        # kleinanzeigen — 1 page
        print("\n=== KLEINANZEIGEN smoke test ===")
        r2 = await sess.get("https://www.kleinanzeigen.de/s-autos/seite:1/c216", impersonate="chrome124", timeout=20)
        rel_re2 = re.compile(r'href="(/s-anzeige/[^"\'?#\s<>]+-\d+)"')
        hits2 = [m for m in rel_re2.findall(r2.text) if re.search(r'\d{6,}', m)]
        hits2 = list(dict.fromkeys(hits2))
        print(f"HTTP {r2.status_code} | listing hrefs: {len(hits2)}")
        for h in hits2[:5]:
            print(f"  https://www.kleinanzeigen.de{h}")

asyncio.run(main())
