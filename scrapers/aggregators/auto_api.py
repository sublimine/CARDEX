"""
auto-api.com connector — paginated listing pull, mapped to canonical records.

Ground truth is the official Go SDK (`github.com/autoapicom/auto-api-go`), read
line-by-line and captured in _research/AGGREGATOR_APIS.md. Every concrete fact
below is `[VERIFIED from docs]`; nothing is invented.

  * Base URL `https://api1.auto-api.com`, version segment `v2` (overridable).
  * Request URL: `GET {base}/api/{version}/{source}/offers`.
  * Auth (GET): API key as the `api_key` query parameter.
  * Envelope: `{ "result": [ { "data": {…} } ], "meta": { "page", "next_page", "limit" } }`.
  * Per-listing `data` (`OfferData`) field names — note the make field is `mark`
    and mileage is `km_age`, which differ from the `/offers` query-param names.
  * Pagination: iterate `meta.next_page` until it is 0/absent (SDK loops on > 0).

The `data` object is mapped into the canonical raw-field dict and graded by the
shared `finalize_record` gate — no bespoke normalization here.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from scrapers.aggregators.transport import (
    AggregatorPull,
    ApiFetcher,
    ApiRequest,
    clean_params,
    finalize_record,
    host_of,
    parse_json,
    raise_for_status,
    require_key,
)

log = logging.getLogger(__name__)

AGGREGATOR = "auto-api"

# [VERIFIED from docs] client.go NewClient defaults.
DEFAULT_BASE_URL = "https://api1.auto-api.com"
DEFAULT_API_VERSION = "v2"

# [VERIFIED from docs] SDK README "Supported sources" table. The SDK uses the
# unhyphenated `mobilede`; the prose docs page spells it `mobile-de` — prefer the
# SDK value (the implemented contract).
SOURCE_SLUGS: frozenset[str] = frozenset(
    {
        "encar",
        "mobilede",
        "autoscout24",
        "che168",
        "dongchedi",
        "guazi",
        "dubicars",
        "dubizzle",
    }
)

# [VERIFIED from docs] types.go OffersParams `url:` tags (SDK query-param names).
# All except `page` are omitempty.
OFFER_FILTER_KEYS: tuple[str, ...] = (
    "brand",
    "model",
    "configuration",
    "complectation",
    "transmission",
    "color",
    "body_type",
    "engine_type",
    "year_from",
    "year_to",
    "mileage_from",
    "mileage_to",
    "price_from",
    "price_to",
)


def _offer_to_raw(data: Mapping[str, Any]) -> tuple[dict, str]:
    """
    Map one `OfferData` object → canonical raw-field dict + the listing URL.

    Field names are verbatim from types.go `OfferData`: make is `mark`, mileage is
    `km_age`, fuel is `engine_type`, transmission is `transmission_type`. Currency
    is not part of OfferData ([not documented publicly]) so it is left absent —
    normalize coerces it to None rather than guessing.
    """
    url = str(data.get("url") or "")
    additional = {
        "generation": data.get("generation"),
        "configuration": data.get("configuration"),
        "complectation": data.get("complectation"),
        "displacement": data.get("displacement"),
        "address": data.get("address"),
        "seller_type": data.get("seller_type"),
        "is_dealer": data.get("is_dealer"),
        "offer_created": data.get("offer_created"),
    }
    raw = {
        "listing_id": data.get("inner_id"),
        "make": data.get("mark"),
        "model": data.get("model"),
        "year": data.get("year"),
        "mileage": data.get("km_age"),
        "fuel": data.get("engine_type"),
        "transmission": data.get("transmission_type"),
        "body": data.get("body_type"),
        "color": data.get("color"),
        "price": data.get("price"),
        "images": data.get("images"),
        "additional": {k: str(v) for k, v in additional.items() if v not in (None, "")},
    }
    return raw, url


async def fetch_offers(
    source: str,
    fetcher: ApiFetcher,
    *,
    api_key: str,
    country: str,
    base_url: str = DEFAULT_BASE_URL,
    api_version: str = DEFAULT_API_VERSION,
    filters: Mapping[str, Any] | None = None,
    start_page: int = 1,
    max_pages: int = 50,
) -> AggregatorPull:
    """
    Pull `GET /api/{version}/{source}/offers`, paginating until `meta.next_page` ends.

    Raises `MissingApiKeyError` before any network call when `api_key` is blank.
    `country` is scrape context supplied by the caller (auto-api sources are global;
    `data` carries only a free-form `address`), passed straight to `to_record`.
    Non-2xx responses raise the precise transport error (auth/rate-limit/generic).
    """
    require_key(AGGREGATOR, api_key)

    offers_url = f"{base_url.rstrip('/')}/api/{api_version}/{source}/offers"
    filter_params = clean_params(
        {k: v for k, v in (filters or {}).items() if k in OFFER_FILTER_KEYS}
    )

    records: list = []
    skipped: list[tuple[str, str]] = []
    seen = 0
    pages_fetched = 0
    page = start_page

    while pages_fetched < max_pages and page > 0:
        params = {"api_key": api_key, "page": str(page), **filter_params}
        resp = await fetcher(ApiRequest(method="GET", url=offers_url, params=params))
        raise_for_status(AGGREGATOR, resp)
        payload = parse_json(AGGREGATOR, resp)
        pages_fetched += 1

        items = payload.get("result") or []
        for item in items:
            seen += 1
            data = item.get("data") or {}
            raw, url = _offer_to_raw(data)
            record, reason = finalize_record(
                raw, source_url=url, source_domain=host_of(url), country=country
            )
            if record is not None:
                records.append(record)
            else:
                ident = str(data.get("inner_id") or url or f"item#{seen}")
                skipped.append((ident, reason))

        meta = payload.get("meta") or {}
        next_page = meta.get("next_page") or 0
        if not isinstance(next_page, int) or next_page <= 0 or next_page == page:
            break
        page = next_page

    return AggregatorPull(
        aggregator=AGGREGATOR,
        source=source,
        country=country.upper(),
        pages_fetched=pages_fetched,
        seen=seen,
        records=tuple(records),
        skipped=tuple(skipped),
    )
