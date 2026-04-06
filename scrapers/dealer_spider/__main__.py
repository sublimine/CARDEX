"""
Entry point for the dealer_spider package.

Usage:
    python -m dealer_spider discover              — run ALL discovery probes
    python -m dealer_spider discover --probe OSM  — run only the OSM probe
    python -m dealer_spider discover --probe OEM --probe INSEE  — run specific probes
    python -m dealer_spider discover --country DE --country FR  — specific countries
    python -m dealer_spider spider                — run the Dealer Web Spider
    python -m dealer_spider all                   — run discover then spider

Available probes: OSM, INSEE (FR only), ZEFIX (CH only), COMMON_CRAWL,
                  GOOGLE_MAPS (requires API key), OEM, PORTAL
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

log = structlog.get_logger()


def _configure_logging() -> None:
    """Set up structlog with human-readable console output."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def _run_discover(
    countries: list[str] | None = None,
    probes: list[str] | None = None,
) -> None:
    from scrapers.dealer_spider.discovery import run as discover_run
    await discover_run(countries=countries, probe_filter=probes)


async def _run_resolve() -> None:
    """Run URL resolver as standalone stream consumer."""
    import asyncpg
    from redis.asyncio import from_url as redis_from_url
    from scrapers.dealer_spider.discovery import URLResolver
    import os

    db_url = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex@localhost:5432/cardex")
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

    pg = await asyncpg.create_pool(db_url, min_size=2, max_size=4)
    rdb = redis_from_url(redis_url, decode_responses=True)

    resolver = URLResolver()
    try:
        await resolver.run(pg, rdb)
    finally:
        await pg.close()
        await rdb.aclose()


async def _run_spider() -> None:
    from scrapers.dealer_spider.spider import run as spider_run
    await spider_run()


async def _run_all(
    countries: list[str] | None = None,
    probes: list[str] | None = None,
) -> None:
    log.info("dealer_spider.all", phase="discovery")
    await _run_discover(countries=countries, probes=probes)
    log.info("dealer_spider.all", phase="spider")
    await _run_spider()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dealer_spider",
        description="CARDEX Dealer Discovery & Spider — Full-Spectrum Multi-Source",
    )
    parser.add_argument(
        "command",
        choices=["discover", "spider", "resolve", "all"],
        help="discover = find dealers via all probes (includes resolver in parallel), "
             "spider = crawl dealer websites, "
             "resolve = standalone URL resolver (stream consumer), "
             "all = discover then spider",
    )
    parser.add_argument(
        "--probe",
        action="append",
        dest="probes",
        metavar="NAME",
        help="Run only specific probes (can be repeated). "
             "Options: OSM, INSEE, ZEFIX, COMMON_CRAWL, GOOGLE_MAPS, OEM, PORTAL",
    )
    parser.add_argument(
        "--country",
        action="append",
        dest="countries",
        metavar="CC",
        help="Run only for specific countries (can be repeated). "
             "Options: DE, ES, FR, NL, BE, CH",
    )
    args = parser.parse_args()

    _configure_logging()

    if args.command == "discover":
        coro = _run_discover(
            countries=args.countries,
            probes=args.probes,
        )
    elif args.command == "resolve":
        coro = _run_resolve()
    elif args.command == "spider":
        coro = _run_spider()
    elif args.command == "all":
        coro = _run_all(
            countries=args.countries,
            probes=args.probes,
        )
    else:
        parser.print_help()
        sys.exit(1)

    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        log.info("dealer_spider.interrupted")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as exc:
        log.error("dealer_spider.fatal", error=str(exc), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
