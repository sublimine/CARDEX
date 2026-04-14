"""
BaseScraper — abstract base class for all CARDEX scraper adapters.

EXHAUSTIVE SCRAPING STRATEGY
─────────────────────────────
Most car portals cap search results at N pages (typically 20-50 × 20-50 results/page).
To get EVERY listing without an artificial hard stop, we decompose queries by:

    make × year × (region if still >cap)

This way each sub-query returns well under the platform cap, and the union covers
the FULL catalog — from the largest dealer group to the smallest garage with 2 cars.

The strategy is:
1. Fetch the platform's make list (or use the canonical make registry below).
2. For each make: iterate all available years (2000 → current year).
3. For each (make, year): page through ALL result pages until the platform returns
   fewer results than page_size (= end of results). No artificial page limit.
4. If a (make, year) query still hits the platform cap: add a region dimension.
5. Save cursor after each (make, year) shard so restarts resume mid-crawl.

Cursor format:  "make:{make}:year:{year}:page:{page}"
Stored in Redis: scraper:cursor:{platform}:{country}

Diff scraping (incremental updates):
- Sort by newest first.
- On subsequent runs, sort by modification date and stop when we reach the
  last-seen listing ID stored in Redis.
- Full re-crawl is triggered if cursor is >7 days old.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import AsyncIterator, AsyncGenerator

import redis.asyncio as aioredis
import structlog

from .frontier_client import FrontierClient
from .gateway_client import GatewayClient
from .http_client import HTTPClient
from .models import RawListing
from .playwright_client import PlaywrightClient
from .robots_checker import RobotsChecker
from .sitemap_parser import SitemapParser

log = structlog.get_logger()

# Canonical make list — every scraper uses this to decompose queries.
# Covers all makes sold in EU over the last 25 years.
# Platforms may have a subset; adapters filter to what's available.
ALL_MAKES: list[str] = [
    # Volume
    "Abarth","Alfa Romeo","Audi","BMW","Chevrolet","Chrysler","Citroën","Cupra",
    "Dacia","Daewoo","DS","Fiat","Ford","Honda","Hyundai","Infiniti","Isuzu",
    "Jaguar","Jeep","Kia","Lada","Lamborghini","Lancia","Land Rover","Lexus",
    "Lincoln","Lotus","Maserati","Mazda","Mercedes-Benz","MG","MINI","Mitsubishi",
    "Nissan","Opel","Peugeot","Porsche","Renault","Rover","Saab","SEAT","Skoda",
    "Smart","SsangYong","Subaru","Suzuki","Tesla","Toyota","Vauxhall","Volkswagen",
    "Volvo",
    # Chinese / EV new entrants
    "BYD","Aiways","NIO","Polestar","Ora","XPENG","Lynk & Co","Maxus","LEVC",
    # Commercial / other
    "Iveco","Mercedes-Benz Vans","Volkswagen Commercial","Ford Transit",
    # Classics / niche
    "Bentley","Ferrari","McLaren","Rolls-Royce","Aston Martin","Bugatti",
    "Koenigsegg","Pagani","Morgan","Caterham","TVR","Donkervoort",
    # Eastern European
    "Wartburg","Trabant","Lada","FSO","Polonez",
]

CURRENT_YEAR = 2025
YEARS = list(range(2000, CURRENT_YEAR + 1))


class BaseScraper(ABC):
    """
    Abstract base for all scraper adapters.

    Subclasses implement:
        async crawl_shard(make: str, year: int) -> AsyncIterator[RawListing]

    OR override crawl() entirely for platforms with different query structures.

    The base run() loop handles:
      - Make × year decomposition
      - Cursor save/restore
      - Gateway ingest with Bloom pre-check
      - Heartbeat to Redis
      - Rate limiting
    """

    platform: str           # e.g. "autoscout24_de"
    country: str            # ISO 3166-1 alpha-2
    domain: str             # rate limiter domain key
    base_url: str = ""      # e.g. "https://www.autoscout24.es" — for robots+sitemap
    listing_patterns: list[str] = []  # URL substrings identifying listing pages
    use_playwright: bool = False
    supports_make_filter: bool = True

    def __init__(self) -> None:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        gateway_url = os.environ.get("GATEWAY_URL", "http://localhost:8090")
        hmac_secret = os.environ.get("GATEWAY_HMAC_SECRET", "")

        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self.gateway = GatewayClient(
            gateway_url=gateway_url,
            hmac_secret=hmac_secret,
            redis_client=self._redis,
        )
        self.http = HTTPClient(
            self.domain,
            country=self.country,
        )
        self.playwright: PlaywrightClient | None = (
            PlaywrightClient(
                headless=os.environ.get("PLAYWRIGHT_HEADLESS", "true").lower() != "false",
                country=self.country,
            )
            if self.use_playwright
            else None
        )
        self.robots = RobotsChecker(self.base_url, self.http) if self.base_url else None
        self.sitemap = SitemapParser(self.http)
        self.frontier = FrontierClient(self._redis, self.platform, self.country)
        self.log = structlog.get_logger(scraper=self.platform, country=self.country)
        self._ban_counts: dict[str, int] = {}  # shard_key → consecutive ban count

    # -------------------------------------------------------------------------
    # Cursor management — granular per (make, year) shard
    # -------------------------------------------------------------------------

    def _shard_cursor_key(self, make: str, year: int) -> str:
        safe_make = make.replace(" ", "_").replace("/", "_").lower()
        return f"scraper:cursor:{self.platform}:{self.country}:{safe_make}:{year}"

    def _global_cursor_key(self) -> str:
        return f"scraper:cursor:{self.platform}:{self.country}:global"

    async def get_shard_cursor(self, make: str, year: int) -> str | None:
        return await self._redis.get(self._shard_cursor_key(make, year))

    async def save_shard_cursor(self, make: str, year: int, cursor: str) -> None:
        await self._redis.set(self._shard_cursor_key(make, year), cursor, ex=8 * 24 * 3600)

    async def mark_shard_done(self, make: str, year: int) -> None:
        """Mark a (make, year) shard as fully scraped (skip on next incremental run)."""
        key = f"scraper:shard_done:{self.platform}:{self.country}"
        safe_make = make.replace(" ", "_").replace("/", "_").lower()
        field = f"{safe_make}:{year}"
        import time
        await self._redis.hset(key, field, int(time.time()))
        await self._redis.expire(key, 8 * 24 * 3600)

    async def is_shard_done(self, make: str, year: int) -> bool:
        """Return True if this shard was fully scraped in the last 7 days."""
        key = f"scraper:shard_done:{self.platform}:{self.country}"
        safe_make = make.replace(" ", "_").replace("/", "_").lower()
        field = f"{safe_make}:{year}"
        val = await self._redis.hget(key, field)
        if not val:
            return False
        import time
        return (time.time() - float(val)) < 7 * 24 * 3600

    # -------------------------------------------------------------------------
    # Heartbeat
    # -------------------------------------------------------------------------

    async def heartbeat(self, total: int, make: str = "", year: int = 0) -> None:
        import time
        key = f"scraper:heartbeat:{self.platform}:{self.country}"
        await self._redis.hset(key, mapping={
            "ts": int(time.time()),
            "count": total,
            "make": make,
            "year": year,
        })
        await self._redis.expire(key, 3600)

    # -------------------------------------------------------------------------
    # Abstract interface — implement one of these
    # -------------------------------------------------------------------------

    async def crawl_shard(self, make: str, year: int) -> AsyncGenerator[RawListing, None]:
        """
        Yield ALL listings for a specific (make, year) combination.
        Must iterate ALL available pages — no artificial stop.
        Stop only when platform returns fewer results than page_size.

        Default implementation calls crawl() — override this for make×year queries.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement crawl_shard(make, year) "
            "or override crawl()"
        )
        # unreachable but satisfies AsyncGenerator typing
        yield  # type: ignore

    async def crawl_listing_url(self, url: str) -> "AsyncGenerator[RawListing, None]":
        """
        Parse a single listing URL and yield RawListing objects.
        Default: not implemented — subclasses that support sitemap mode override this.
        """
        return
        yield  # make it an async generator

    async def crawl(self) -> AsyncGenerator[RawListing, None]:
        """
        Crawl strategy (in order):
        1. Sitemap mode — if base_url and listing_patterns are set, parse sitemaps
           for 100% URL coverage, then call crawl_listing_url() for each.
        2. Make×year fallback — for portals without sitemaps or JSON APIs,
           use the decomposed query strategy.

        Subclasses can override crawl() entirely for custom strategies.
        """
        import time

        # ── Strategy 1: Sitemap (100% coverage, cleanest) ─────────────────────
        if self.base_url and self.listing_patterns:
            known_sitemaps = self.robots.sitemaps if self.robots else []
            count = 0
            async for url in self.sitemap.listing_urls(
                base_url=self.base_url,
                listing_patterns=self.listing_patterns,
                known_sitemaps=known_sitemaps,
            ):
                if self.robots and not self.robots.can_fetch(url.split(self.base_url)[-1]):
                    continue
                try:
                    async for listing in self.crawl_listing_url(url):
                        count += 1
                        yield listing
                except Exception as e:
                    self.log.error("scraper.listing_error", url=url, error=str(e))

            if count > 0:
                self.log.info("scraper.sitemap_complete", count=count)
                return
            # If sitemap yielded 0 listings (crawl_listing_url not implemented),
            # fall through to make×year strategy

        # ── Strategy 2: Frontier-directed make×year decomposition ─────────────
        # If the frontier service has published priorities, crawl high-priority
        # shards first. Otherwise, fall back to blind ALL_MAKES × YEARS iteration.

        ordered_shards = await self.frontier.get_ordered_shards()
        if ordered_shards:
            self.log.info("scraper.frontier_directed", shard_count=len(ordered_shards))
            shard_iter = [(make, year) for make, year, _ in ordered_shards]
        else:
            self.log.info("scraper.fallback_blind_iteration")
            shard_iter = [(make, year) for make in ALL_MAKES for year in reversed(YEARS)]

        for make, year in shard_iter:
            if await self.is_shard_done(make, year):
                self.log.debug("scraper.shard_skip", make=make, year=year)
                continue

            shard_key = f"{make}:{year}"
            try:
                count = 0
                async for listing in self.crawl_shard(make, year):
                    count += 1
                    self._ban_counts[shard_key] = 0  # reset on success
                    yield listing
                await self.mark_shard_done(make, year)
                await self.frontier.report_result(make, year, count)
                self.log.info("scraper.shard_complete", make=make, year=year, count=count)

            except Exception as e:
                err_str = str(e).lower()
                is_ban = any(kw in err_str for kw in ("ban", "403", "blocked", "access denied", "captcha"))
                self._ban_counts[shard_key] = self._ban_counts.get(shard_key, 0) + 1
                consecutive = self._ban_counts[shard_key]

                if is_ban and consecutive >= 3:
                    self.log.warning(
                        "scraper.shard_ban_pause",
                        make=make, year=year, consecutive=consecutive,
                    )
                    # Park shard for 1 hour by writing a temp cursor
                    await self._redis.set(
                        f"scraper:ban_pause:{self.platform}:{self.country}:{shard_key}",
                        int(time.time()),
                        ex=3600,
                    )
                    self._ban_counts[shard_key] = 0
                else:
                    self.log.error(
                        "scraper.shard_error",
                        make=make, year=year, error=str(e), consecutive=consecutive,
                    )

    # -------------------------------------------------------------------------
    # Main run loop
    # -------------------------------------------------------------------------

    async def run(self) -> None:
        self.log.info("scraper.run.start", platform=self.platform, country=self.country)
        total = accepted = skipped = errors = 0

        ctx_managers = [self.http]
        if self.playwright:
            ctx_managers.append(self.playwright)

        entered = []
        for cm in ctx_managers:
            await cm.__aenter__()
            entered.append(cm)

        try:
            # Load rate limits from Redis
            await self.http.rate_limiter.load_from_redis(self._redis)

            # Load robots.txt — discover sitemaps + crawl-delay
            if self.robots:
                await self.robots.load()
                if self.robots.crawl_delay:
                    self.http.rate_limiter.rps = 1.0 / self.robots.crawl_delay
                    self.log.info(
                        "scraper.crawl_delay_applied",
                        delay=self.robots.crawl_delay,
                        sitemaps=len(self.robots.sitemaps),
                    )

            async for listing in self.crawl():
                total += 1
                try:
                    ok = await self.gateway.ingest(listing)
                    if ok:
                        accepted += 1
                    else:
                        skipped += 1
                except Exception as e:
                    errors += 1
                    self.log.error("scraper.ingest_error", error=str(e), url=listing.source_url)

                if total % 500 == 0:
                    await self.heartbeat(total)
                    self.log.info(
                        "scraper.progress",
                        total=total, accepted=accepted,
                        skipped=skipped, errors=errors,
                    )

        finally:
            for cm in reversed(entered):
                try:
                    await cm.__aexit__(None, None, None)
                except Exception:
                    pass
            await self.gateway.close()
            await self._redis.aclose()

        self.log.info(
            "scraper.run.complete",
            total=total, accepted=accepted, skipped=skipped, errors=errors,
        )
