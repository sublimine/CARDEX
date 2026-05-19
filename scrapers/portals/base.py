"""
BasePortalScraper — contrato que todo scraper de portal debe implementar.

Cada portal hereda de esta clase y define:
  - DOMAIN: str — dominio canónico
  - COUNTRY: str — código de país
  - TIER: Tier — tier baseline (puede escalarse)
  - partition_strategy() — cómo subdividir para superar el cap de 2000 resultados
  - fetch_page(session, page_num, params) → list[str]
  - extract_urls(html_or_json, base_url) → list[str]

El coordinator NO llama fetch directamente.
Llama run() que gestiona: identidad, proxy, warming check, circuit breaker,
  intent engine, delta, métricas.

No implementar lógica de retry, proxy, o identidad en los scrapers individuales.
Todo eso es responsabilidad del coordinator + engine/.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from scrapers.common.indexer import run_portal
from scrapers.engine.router.domain_map import Tier
from scrapers.engine.session.warming import enforce_no_extraction_before_warming

log = logging.getLogger(__name__)


class BasePortalScraper(ABC):

    DOMAIN: str = ""
    COUNTRY: str = ""
    TIER: Tier = Tier.T1

    @abstractmethod
    def partition_params(self) -> list[dict[str, Any]]:
        """
        Return list of parameter dicts that partition the portal's inventory.
        Each param dict is one segment (e.g. year_band + price_ceiling + fuel).
        Segments must be non-overlapping and collectively exhaustive.
        A segment that hits result cap MUST be further subdivided.
        """
        ...

    @abstractmethod
    async def fetch_segment(
        self,
        session: Any,          # curl_cffi AsyncSession (T1) or Camoufox page (T2/T3)
        params: dict[str, Any],
        page_num: int,
    ) -> list[str]:
        """Fetch one page of one segment. Return deep-link URLs only. No root domains."""
        ...

    @abstractmethod
    def is_result_cap_hit(self, urls: list[str]) -> bool:
        """True if page count × page_size == max_results (pagination cap reached)."""
        ...

    async def run(self) -> None:
        """
        Full scrape cycle. Called by coordinator.
        Handles: warming check, identity assignment, proxy assignment,
                 circuit breaker, all segments, delta, metrics.
        Do NOT override — implement fetch_segment and partition_params.
        """
        raise NotImplementedError
