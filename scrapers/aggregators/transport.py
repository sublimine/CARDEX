"""
Injected transport + error taxonomy for aggregator (paid-API) connectors.

The aggregator connectors (auto-api.com, carapis.com) never own an HTTP client.
A `Fetcher` is injected exactly as the generic dealer extractor injects its
`Fetcher` (pipeline.generic_extractor) — so orchestration stays pure, DB-free and
unit-testable against in-memory fixtures, with no curl_cffi/httpx in the hot path.

Honesty contract (PLAN.md §0, Class B):
  * These APIs are paid and key-gated. A connector raises `MissingApiKeyError`
    *before any network call* when no key is supplied — the `[NEEDS-KEY]` state is
    surfaced honestly, never faked with stub data.
  * Non-2xx responses map to a precise error: 401/403 → auth, 429 → rate-limit,
    everything else → a generic `AggregatorError` carrying the status and body.

The per-listing payload of either API is mapped into the canonical raw-field dict
and handed to `pipeline.normalize.to_record`, then graded by the same completeness
+ structural gates every scraped record passes (`finalize_record`). No bespoke
normalization lives here: aggregator data flows through the one canonical pipeline.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Awaitable, Callable, Mapping

from scrapers.pipeline.normalize import to_record
from scrapers.pipeline.quality import evaluate
from scrapers.pipeline.schema import VehicleRecord
from urllib.parse import urlparse


# ── injected transport ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ApiRequest:
    """One outbound API call. Fully described so a fetcher needs no extra context."""

    method: str  # "GET" or "POST"
    url: str  # absolute, without query string (params carried separately)
    params: Mapping[str, str] = field(default_factory=dict)
    headers: Mapping[str, str] = field(default_factory=dict)
    json_body: dict | None = None


@dataclass(frozen=True)
class ApiResponse:
    """One API response. `body` is raw bytes; status is the real HTTP status code."""

    status_code: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """UTF-8 decode of the body, replacing undecodable bytes (never raises)."""
        return self.body.decode("utf-8", errors="replace")


# A Fetcher takes a fully-described ApiRequest and resolves to an ApiResponse.
# Implementations wrap curl_cffi / httpx; tests pass an in-memory fake. It must
# NOT raise for ordinary HTTP errors (return the status) — only for transport
# faults (DNS, connection reset, timeout).
ApiFetcher = Callable[[ApiRequest], Awaitable[ApiResponse]]


# ── error taxonomy ──────────────────────────────────────────────────────────
class AggregatorError(Exception):
    """Base for every aggregator failure. Carries the aggregator name + context."""

    def __init__(
        self,
        aggregator: str,
        message: str,
        *,
        status_code: int | None = None,
        body: str | None = None,
    ) -> None:
        self.aggregator = aggregator
        self.status_code = status_code
        self.body = body
        prefix = f"[{aggregator}]"
        if status_code is not None:
            prefix += f" HTTP {status_code}"
        super().__init__(f"{prefix} {message}")


class MissingApiKeyError(AggregatorError):
    """No API key supplied — raised before any network call (honest `[NEEDS-KEY]`)."""

    def __init__(self, aggregator: str) -> None:
        super().__init__(
            aggregator,
            "no API key supplied — this is a paid, key-gated API ([NEEDS-KEY]); "
            "set the key before calling.",
        )


class AggregatorAuthError(AggregatorError):
    """401/403 — the supplied key was rejected."""


class AggregatorRateLimited(AggregatorError):
    """429 — over the plan's request quota. `retry_after` is seconds when known."""

    def __init__(
        self,
        aggregator: str,
        message: str,
        *,
        status_code: int,
        body: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(aggregator, message, status_code=status_code, body=body)


# ── shared helpers ────────────────────────────────────────────────────────────
def require_key(aggregator: str, api_key: str | None) -> str:
    """Return the key, or raise MissingApiKeyError when it is absent/blank."""
    if not api_key or not api_key.strip():
        raise MissingApiKeyError(aggregator)
    return api_key


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """Case-insensitive header lookup; None when absent."""
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None


def raise_for_status(aggregator: str, resp: ApiResponse) -> None:
    """Map a non-2xx response onto the precise error type. No-op on 2xx."""
    code = resp.status_code
    if 200 <= code < 300:
        return
    body = resp.text[:500]
    if code in (401, 403):
        raise AggregatorAuthError(
            aggregator, "authentication rejected", status_code=code, body=body
        )
    if code == 429:
        raw_retry = _header(resp.headers, "Retry-After") or _header(
            resp.headers, "X-RateLimit-Reset"
        )
        retry_after: int | None = None
        if raw_retry is not None:
            try:
                retry_after = int(raw_retry)
            except (TypeError, ValueError):
                retry_after = None
        raise AggregatorRateLimited(
            aggregator,
            "rate limit exceeded",
            status_code=code,
            body=body,
            retry_after=retry_after,
        )
    raise AggregatorError(aggregator, "request failed", status_code=code, body=body)


def parse_json(aggregator: str, resp: ApiResponse) -> Any:
    """Decode the response body as JSON, raising AggregatorError on malformed bodies."""
    try:
        return json.loads(resp.body)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AggregatorError(
            aggregator,
            f"malformed JSON response: {exc}",
            status_code=resp.status_code,
            body=resp.text[:500],
        ) from exc


def host_of(url: str) -> str:
    """Lowercased registrable host without a leading 'www.'; '' when unparseable."""
    if not url:
        return ""
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def finalize_record(
    raw: dict,
    *,
    source_url: str,
    source_domain: str,
    country: str,
    current_year: int | None = None,
) -> tuple[VehicleRecord | None, str]:
    """
    Turn one mapped raw-field dict into a graded VehicleRecord.

    Reuses the exact pipeline every scraped record passes:
      1. `to_record` — canonical normalization (enums, Decimal money, VIN, images).
      2. completeness — `missing_critical` (make/model/year/price/url/image≥1).
      3. GATE 1 structural — price/year/mileage ranges + deep-link URL (no HTML, so
         poison/GATE 2 is intentionally skipped: that defends HTML scraping, not a
         structured paid feed).

    Returns `(record, "ok")` when ingestible, else `(None, reason)` where reason is
    `missing_critical:<fields>` or the comma-joined structural failure names.
    """
    year_ceiling = date.today().year if current_year is None else current_year
    record = to_record(
        raw, source_url=source_url, source_domain=source_domain, country=country
    )
    missing = record.missing_critical()
    if missing:
        return None, "missing_critical:" + ",".join(missing)
    verdict = evaluate(record, current_year=year_ceiling)
    if not verdict.ok:
        return None, verdict.reason
    return record, "ok"


def clean_params(values: Mapping[str, Any]) -> dict[str, str]:
    """
    Stringify query params, dropping omitempty values (None, "", 0).

    Mirrors the auto-api Go SDK's `encodeParams` omitempty rule so filter args
    behave identically: a zero int or empty string is omitted, not sent as "0"/"".
    """
    out: dict[str, str] = {}
    for key, value in values.items():
        if value is None or value == "" or value == 0:
            continue
        out[key] = str(value)
    return out


# ── result envelope ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class AggregatorPull:
    """Outcome of pulling listings from one aggregator source. Pure telemetry + rows."""

    aggregator: str
    source: str
    country: str
    pages_fetched: int
    seen: int  # raw listing objects encountered across all pages
    records: tuple[VehicleRecord, ...]
    skipped: tuple[tuple[str, str], ...]  # (identifier, reason) for rejected listings

    @property
    def extracted(self) -> int:
        """Count of ingestible records."""
        return len(self.records)

    @property
    def success_rate(self) -> float:
        """Fraction of seen listings that produced an ingestible record (0.0 when none)."""
        return self.extracted / self.seen if self.seen else 0.0
