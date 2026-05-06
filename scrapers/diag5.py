"""Diag5 — find exact AS24 listing URL pattern in HTML."""
import asyncio, re
from curl_cffi.requests import AsyncSession
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def main():
    async with AsyncSession() as sess:
        r = await sess.get(
            "https://www.autoscout24.de/lst?atype=C&desc=0&sort=standard&year_from=2020&year_to=2022&price_to=30000&page=1",
            impersonate="chrome124", timeout=20
        )
        text = r.text
        print(f"HTTP {r.status_code} | {len(text)} chars")

        # Try different patterns
        patterns = [
            (r'"(/angebote/[^"\\]{20,})"',           "JSON double-quoted"),
            (r"'(/angebote/[^'\\]{20,})'",            "JSON single-quoted"),
            (r'href=\\?"(/angebote/[^"\\]{10,})',     "href= escaped"),
            (r'/angebote/[a-z0-9][a-z0-9-]+-[0-9a-f-]{36}', "UUID pattern direct"),
            (r'angebote\\/[^"\'\\]{20,}',             "escaped slash in JSON"),
            (r'"url"\s*:\s*"(/angebote/[^"]+)"',      '"url": pattern'),
        ]
        for pat, name in patterns:
            hits = re.findall(pat, text, re.I)
            hits = list(dict.fromkeys(hits))
            print(f"\n[{name}] ({len(hits)} hits)")
            for h in hits[:3]:
                print(f"  {h[:120]}")

        # Also dump the 200-char context around any /angebote/ occurrence
        idx = text.find('/angebote/')
        if idx >= 0:
            print(f"\n[CONTEXT around first /angebote/]")
            print(repr(text[max(0,idx-30):idx+150]))

asyncio.run(main())
