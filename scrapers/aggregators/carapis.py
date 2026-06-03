"""
carapis.com connector — v2 "unified listings" surface, mapped to canonical records.

carapis.com publishes THREE mutually inconsistent API surfaces (see
_research/AGGREGATOR_APIS.md). This connector implements **Surface A**, the v2
unified listings API documented on carapis.com/api/intro, because it is the only
surface whose request shape AND per-listing field names are both published
verbatim. Every fact below is `[VERIFIED from docs]`; nothing is invented.

  * Request: `GET https://api.carapis.com/v2/listings?source=<slug>&limit=N`.
  * Auth: `Authorization: Bearer <API_KEY>` header.
  * Envelope: `{ "count", "page", "limit", "results": [ … ] }`.
  * Per-listing fields: `id, source, make, model, year, mileage, price, currency,
    location, fuel_type, transmission, photos, dealer, url`.
  * Pagination: envelope carries `count`/`page`/`limit`; request `page`+`limit`.
    Cursor pagination is [not documented publicly], so we page by incrementing
    `page` until a short/empty page or the `count` total is reached.

Listings are mapped into the canonical raw-field dict and graded by the shared
`finalize_record` gate. Body/colour are not in the v2 schema, so they stay absent.
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

AGGREGATOR = "carapis"

# [VERIFIED from docs] carapis.com/api/intro: requests to https://api.carapis.com/v2/listings.
DEFAULT_BASE_URL = "https://api.carapis.com/v2"
DEFAULT_LIMIT = 100  # [VERIFIED from docs] caller-tunable; v2 page size is `limit`.

# [VERIFIED from docs] carapis.com/api/intro per-listing field names (Surface A).
def _listing_to_raw(listing: Mapping[str, Any]) -> tuple[dict, str]:
    """
    Map one v2 listing object → canonical raw-field dict + the listing URL.

    Field names are verbatim from carapis.com/api/intro: `make`, `model`, `year`,
    `mileage`, `price`, `currency`, `fuel_type`, `transmission`, `photos` (images),
    `url`. Body type and colour are absent from the documented v2 schema, so they
    are not invented — normalize leaves them None.
    """
    url = str(listing.get("url") or "")
    additional = {
        "location": listing.get("location"),
        "dealer": listing.get("dealer"),
        "source": listing.get("source"),
    }
    raw = {
        "listing_id": listing.get("id"),
        "make": listing.get("make"),
        "model": listing.get("model"),
        "year": listing.get("year"),
        "mileage": listing.get("mileage"),
        "fuel": listing.get("fuel_type"),
        "transmission": listing.get("transmission"),
        "price": listing.get("price"),
        "currency": listing.get("currency"),
        "images": listing.get("photos"),
        "additional": {
            k: str(v) for k, v in additional.items() if v not in (None, "")
        },
    }
    return raw, url


async def fetch_listings(
    source: str,
    fetcher: ApiFetcher,
    *,
    api_key: str,
    country: str,
    base_url: str = DEFAULT_BASE_URL,
    limit: int = DEFAULT_LIMIT,
    filters: Mapping[str, Any] | None = None,
    start_page: int = 1,
    max_pages: int = 50,
) -> AggregatorPull:
    """
    Pull `GET /v2/listings?source=…&limit=…`, paging until a short page or `count`.

    Raises `MissingApiKeyError` before any network call when `api_key` is blank.
    The key is sent as `Authorization: Bearer <key>`. `country` is caller-supplied
    scrape context passed to `to_record`. Non-2xx responses raise the precise
    transport error (auth/rate-limit/generic).
    """
    require_key(AGGREGATOR, api_key)

    listings_url = f"{base_url.rstrip('/')}/listings"
    headers = {"Authorization": f"Bearer {api_key}"}
    extra = clean_params(filters or {})

    records: list = []
    skipped: list[tuple[str, str]] = []
    seen = 0
    pages_fetched = 0
    collected = 0
    page = start_page

    while pages_fetched < max_pages:
        params = {"source": source, "limit": str(limit), "page": str(page), **extra}
        resp = await fetcher(
            ApiRequest(method="GET", url=listings_url, params=params, headers=headers)
        )
        raise_for_status(AGGREGATOR, resp)
        payload = parse_json(AGGREGATOR, resp)
        pages_fetched += 1

        results = payload.get("results") or []
        for listing in results:
            seen += 1
            raw, url = _listing_to_raw(listing)
            record, reason = finalize_record(
                raw, source_url=url, source_domain=host_of(url), country=country
            )
            if record is not None:
                records.append(record)
            else:
                ident = str(listing.get("id") or url or f"item#{seen}")
                skipped.append((ident, reason))

        collected += len(results)
        count = payload.get("count")
        if not results or len(results) < limit:
            break
        if isinstance(count, int) and collected >= count:
            break
        page += 1

    return AggregatorPull(
        aggregator=AGGREGATOR,
        source=source,
        country=country.upper(),
        pages_fetched=pages_fetched,
        seen=seen,
        records=tuple(records),
        skipped=tuple(skipped),
    )
