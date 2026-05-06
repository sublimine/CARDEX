"""Final smoke test — AS24 JSON regex fix."""
import asyncio, re
from curl_cffi.requests import AsyncSession
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    json_re = re.compile(r'"(/angebote/[^"\\]{20,})"', re.I)
    async with AsyncSession() as sess:
        r = await sess.get(
            "https://www.autoscout24.de/lst?atype=C&desc=0&sort=standard&year_from=2020&year_to=2022&price_to=30000&page=1",
            impersonate="chrome124", timeout=20
        )
        hits = list(dict.fromkeys(json_re.findall(r.text)))
        print(f"HTTP {r.status_code} | AS24 DE listing URLs found: {len(hits)}")
        for h in hits[:5]:
            print(f"  https://www.autoscout24.de{h}")

asyncio.run(main())
