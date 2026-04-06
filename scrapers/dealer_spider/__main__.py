"""
Entry point for the dealer_spider package.

Usage:
    python -m dealer_spider discover   — run the Discovery Orchestrator
    python -m dealer_spider spider     — run the Dealer Web Spider
    python -m dealer_spider all        — run discover then spider
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


async def _run_discover() -> None:
    from scrapers.dealer_spider.discovery import run as discover_run
    await discover_run()


async def _run_spider() -> None:
    from scrapers.dealer_spider.spider import run as spider_run
    await spider_run()


async def _run_all() -> None:
    log.info("dealer_spider.all", phase="discovery")
    await _run_discover()
    log.info("dealer_spider.all", phase="spider")
    await _run_spider()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dealer_spider",
        description="CARDEX Dealer Discovery & Spider",
    )
    parser.add_argument(
        "command",
        choices=["discover", "spider", "all"],
        help="discover = find dealers via Google Places, "
             "spider = crawl dealer websites, "
             "all = discover then spider",
    )
    args = parser.parse_args()

    _configure_logging()

    coro = {
        "discover": _run_discover,
        "spider": _run_spider,
        "all": _run_all,
    }[args.command]

    try:
        asyncio.run(coro())
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
