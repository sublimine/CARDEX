"""Read autotrack sitemap index to find listing sitemaps."""
import asyncio, re
from curl_cffi.requests import AsyncSession

async def main():
    async with AsyncSession() as sess:
        r = await sess.get("https://www.autotrack.nl/sitemap.xml", impersonate="chrome124", timeout=15)
        print(f"HTTP {r.status_code} | {len(r.text)} chars")
        locs = re.findall(r'<loc>([^<]+)</loc>', r.text)
        print(f"Sitemap entries: {len(locs)}")
        for loc in locs[:20]:
            print(f"  {loc}")
        # Find which ones are vehicle/listing sitemaps
        vehicle_maps = [l for l in locs if any(x in l.lower() for x in
                        ['occasion', 'auto', 'voertuig', 'vehicle', 'car'])]
        print(f"\nVehicle-related: {vehicle_maps[:10]}")
        # Fetch one to see URL pattern
        if vehicle_maps:
            r2 = await sess.get(vehicle_maps[0], impersonate="chrome124", timeout=15)
            print(f"\nFirst vehicle sitemap: {r2.status_code} | {len(r2.text)} chars")
            urls = re.findall(r'<loc>([^<]+)</loc>', r2.text)
            print(f"URLs: {len(urls)}, examples: {urls[:5]}")

asyncio.run(main())
