"""
Mobile RE client — acceso directo a APIs internas de apps móviles.

T0: sin anti-bot web. 80x más barato que T2 (Camoufox).

Proceso de RE por portal (ver SCRAPING_ENGINE.md §A7):
  1. mitmproxy + frida unpinning → dump de tráfico
  2. mitmproxy2swagger → spec OpenAPI preliminar
  3. Identificar endpoints de búsqueda + listing
  4. Implementar client aquí con auth + token refresh

Portales con RE confirmado/viable:
  - mobile.de: Ad-Stream WSS (ya en clients/mobile_de/)
  - autoscout24: misma API que web + X-AS24-App header
  - leboncoin: RE móvil = bypass total de DataDome web
  - lacentrale: idem
  - wallapop: API bien documentada externamente
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MobileAPIResult:
    listing_urls: list[str]
    next_page_token: str | None
    total_count: int | None


class BaseMobileClient(ABC):

    PORTAL: str = ""
    COUNTRY: str = ""

    @abstractmethod
    async def authenticate(self) -> None:
        """Obtain or refresh auth token. Called on init and when 401 received."""
        ...

    @abstractmethod
    async def search(
        self,
        params: dict,
        page_token: str | None = None,
    ) -> MobileAPIResult:
        """
        Execute search request and return listing URLs + pagination token.
        params: {make?, model?, year_min?, year_max?, price_max?, fuel?}
        """
        ...

    async def exhaust(self, params: dict) -> list[str]:
        """Paginate until no next_page_token. Returns all listing URLs."""
        all_urls: list[str] = []
        token = None
        while True:
            result = await self.search(params, token)
            all_urls.extend(result.listing_urls)
            if not result.next_page_token:
                break
            token = result.next_page_token
        return all_urls
