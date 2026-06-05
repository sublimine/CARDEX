"""
Aggregator (paid-API) connectors — Class B sources (PLAN.md §0).

These connectors pull pre-extracted inventory from commercial aggregators
(auto-api.com, carapis.com). They are key-gated: without a paid API key a
`MissingApiKeyError` is raised before any network call, so the `[NEEDS-KEY]`
state is honest and never faked. Each connector maps the aggregator's VERIFIED
per-listing schema into the one canonical raw-field dict and runs it through the
same `pipeline.normalize` + completeness/structural gates as scraped records.

The HTTP transport is injected (`ApiFetcher`), exactly like the generic dealer
extractor — orchestration stays pure and unit-testable against in-memory fixtures.
"""
from scrapers.aggregators import auto_api, carapis
from scrapers.aggregators.transport import (
    AggregatorAuthError,
    AggregatorError,
    AggregatorPull,
    AggregatorRateLimited,
    ApiFetcher,
    ApiRequest,
    ApiResponse,
    MissingApiKeyError,
    host_of,
)

__all__ = [
    "auto_api",
    "carapis",
    "AggregatorError",
    "AggregatorAuthError",
    "AggregatorRateLimited",
    "MissingApiKeyError",
    "AggregatorPull",
    "ApiRequest",
    "ApiResponse",
    "ApiFetcher",
    "host_of",
]
