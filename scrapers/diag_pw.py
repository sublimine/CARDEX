"""Playwright smoke test â€” verify stealth works against CF and DPG WAF."""
import asyncio, re
from scrapers.common.pw_base import make_stealth_browser, make_stealth_page


TESTS = [
    ("lacentrale.fr", "https://www.lacentrale.fr/listing?page=1", "fr-FR",
     r'/auto-occasion-annonce-\d+\.html'),
    ("leboncoin.fr", "https://www.leboncoin.fr/recherche?category=2&page=1", "fr-FR",
     r'/voitures/\d+\.htm'),
    ("autotrack.nl", "https://www.autotrack.nl/occasion/personen?page=1", "nl-NL",
     r'/autos/[^"?#\s]+/\d+/'),
    ("mobile.de", "https://suchen.mobile.de/fahrzeuge/search.html?categories=CAR&pageNumber=1", "de-DE",
     r'/fahrzeuge/details\.html\?id=\d+'),
]

async def main():
    pw, browser = await make_stealth_browser()
    try:
        for name, url, locale, pattern in TESTS:
            print(f"\n{'='*50}\n{name}")
            page = await make_stealth_page(browser, locale)
            captured = []

            async def on_resp(resp):
                try:
                    body = await resp.text()
                    hits = re.findall(pattern, body, re.I)
                    if hits:
                        captured.extend(hits)
                        print(f"  XHR {resp.url[:60]} -> {len(hits)} hits")
                except Exception:
                    pass

            page.on("response", on_resp)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"  nav error: {e}")

            dom = await page.content()
            dom_hits = re.findall(pattern, dom, re.I)
            total = list(dict.fromkeys(captured + dom_hits))
            print(f"  DOM hits: {len(dom_hits)} | XHR hits: {len(captured)} | TOTAL: {len(total)}")
            if total:
                print(f"  examples: {total[:3]}")
            else:
                title = re.search(r'<title[^>]*>([^<]{0,60})', dom, re.I)
                print(f"  TITLE: {title.group(1) if title else 'n/a'}")
                print(f"  DOM size: {len(dom)}")

            await page.close()

    finally:
        await browser.close()
        await pw.stop()
    print("\nDONE")

asyncio.run(main())

