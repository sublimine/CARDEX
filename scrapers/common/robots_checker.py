"""
robots_checker.py — Robots.txt parser and compliance checker.

CARDEX respects robots.txt as a polite indexer.
This module also extracts sitemap URLs declared in robots.txt,
which is how we discover the full listing catalog.

Usage:
    checker = RobotsChecker("https://www.autoscout24.es", http_client)
    await checker.load()
    sitemaps = checker.sitemaps          # list of sitemap URLs
    allowed  = checker.can_fetch("/s/")  # True/False
    delay    = checker.crawl_delay       # seconds, or None
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import structlog

log = structlog.get_logger()

_DEFAULT_AGENT = "CardexBot"


class RobotsChecker:
    """
    Fetches and parses robots.txt for a given base URL.
    Extracts sitemap declarations and crawl-delay directives.
    """

    def __init__(self, base_url: str, http_client: any) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = http_client
        self.sitemaps: list[str] = []
        self.crawl_delay: Optional[float] = None
        self._disallow: list[str] = []
        self._allow: list[str] = []
        self._loaded = False

    async def load(self) -> None:
        robots_url = f"{self.base_url}/robots.txt"
        try:
            text = await self._http.get_text(robots_url)
            self._parse(text)
            self._loaded = True
            log.info(
                "robots.loaded",
                base=self.base_url,
                sitemaps=len(self.sitemaps),
                crawl_delay=self.crawl_delay,
            )
        except Exception as e:
            log.warning("robots.fetch_failed", base=self.base_url, error=str(e))
            # Fail open — allow crawling if robots.txt unreachable

    def _parse(self, text: str) -> None:
        """Parse robots.txt — extract directives for CardexBot and * agents."""
        current_agents: list[str] = []
        applies_to_us = False

        for raw_line in text.splitlines():
            line = raw_line.strip()

            # Sitemap declarations apply globally (not per-agent)
            if line.lower().startswith("sitemap:"):
                url = line.split(":", 1)[1].strip()
                if url:
                    self.sitemaps.append(url)
                continue

            if not line or line.startswith("#"):
                if current_agents:
                    current_agents = []
                    applies_to_us = False
                continue

            if line.lower().startswith("user-agent:"):
                agent = line.split(":", 1)[1].strip()
                current_agents.append(agent)
                applies_to_us = any(
                    a == "*" or _DEFAULT_AGENT.lower() in a.lower()
                    for a in current_agents
                )
                continue

            if not applies_to_us:
                continue

            if line.lower().startswith("disallow:"):
                path = line.split(":", 1)[1].strip()
                if path:
                    self._disallow.append(path)

            elif line.lower().startswith("allow:"):
                path = line.split(":", 1)[1].strip()
                if path:
                    self._allow.append(path)

            elif line.lower().startswith("crawl-delay:"):
                try:
                    self.crawl_delay = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass

    def can_fetch(self, path: str) -> bool:
        """Return True if we are allowed to fetch this path."""
        if not self._loaded:
            return True  # fail open

        # Explicit Allow takes precedence over Disallow
        for allow_path in self._allow:
            if path.startswith(allow_path):
                return True

        for disallow_path in self._disallow:
            if disallow_path and path.startswith(disallow_path):
                return False

        return True

    def effective_delay(self, default_rps: float = 0.3) -> float:
        """
        Return the effective crawl delay in seconds.
        Respects Crawl-Delay directive if present, otherwise uses default_rps.
        """
        if self.crawl_delay is not None:
            return self.crawl_delay
        return 1.0 / default_rps
