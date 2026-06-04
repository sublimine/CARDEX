"""
Delta engine — pure set-diff + price-change detection.

Mirrors the invariants of common/indexer.delta (SEEN/GONE, in-process set diff,
zero-touch on unchanged rows) but as a *pure function* over plain mappings: no
Postgres, no Redis, no event loop. The coordinator feeds it the stored state and
the freshly scraped cycle; it returns what changed. That decoupling is what makes
the diff logic unit-testable in isolation (the previous monolith could only test
it against a live DB).

Adds the §C1 improvement the legacy indexer lacked: a per-listing `price_hash`
so a price/availability change emits a PRICE_CHANGE without a full content diff.

url_hash is reimplemented here (sha256[:32], identical to indexer.url_hash) so this
module imports nothing heavy — importing indexer would drag in asyncpg/redis.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

from scrapers.pipeline.schema import VehicleRecord, price_hash

# Sentinel for "URL seen this cycle but its price is unknown" (URL-only index pass).
PRICE_UNKNOWN = ""


def url_hash(url: str) -> str:
    """32-hex-char SHA256 prefix — byte-identical to common.indexer.url_hash."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def is_deep_link(url: str) -> bool:
    """Reject root/empty paths — a listing URL must carry a meaningful path (indexer guard)."""
    path = urlparse(url).path
    return bool(path) and path not in ("/", "")


@dataclass(frozen=True)
class DeltaResult:
    """Outcome of one cycle diff. Hashes are url_hashes; counts are derived."""

    new: tuple[str, ...]
    gone: tuple[str, ...]
    price_changed: tuple[str, ...]
    unchanged: int

    @property
    def new_count(self) -> int:
        return len(self.new)

    @property
    def gone_count(self) -> int:
        return len(self.gone)

    @property
    def price_changed_count(self) -> int:
        return len(self.price_changed)


def cycle_from_urls(urls: Iterable[str]) -> dict[str, str]:
    """Build a cycle map {url_hash: PRICE_UNKNOWN} from raw URLs, dropping non-deep-links."""
    out: dict[str, str] = {}
    for url in urls:
        if is_deep_link(url):
            out[url_hash(url)] = PRICE_UNKNOWN
    return out


def cycle_from_records(records: Iterable[VehicleRecord]) -> dict[str, str]:
    """Build a cycle map {url_hash: price_hash} from enriched records, dropping non-deep-links."""
    out: dict[str, str] = {}
    for rec in records:
        if is_deep_link(rec.source_url):
            out[url_hash(rec.source_url)] = price_hash(rec)
    return out


def compute_delta(
    previous: Mapping[str, str],
    current: Mapping[str, str],
) -> DeltaResult:
    """
    Diff stored state against the current cycle.

      new           in current, absent from previous
      gone          in previous, absent from current
      price_changed in both, both prices known, and they differ
      unchanged     in both, not counted as price_changed

    A change is only asserted when *both* sides carry a known price_hash; a recheck
    that did not re-read the price (PRICE_UNKNOWN) never spuriously fires a change.
    """
    prev_keys = set(previous)
    cur_keys = set(current)

    new = sorted(cur_keys - prev_keys)
    gone = sorted(prev_keys - cur_keys)

    price_changed: list[str] = []
    unchanged = 0
    for h in cur_keys & prev_keys:
        before, after = previous[h], current[h]
        if before and after and before != after:
            price_changed.append(h)
        else:
            unchanged += 1

    return DeltaResult(
        new=tuple(new),
        gone=tuple(gone),
        price_changed=tuple(sorted(price_changed)),
        unchanged=unchanged,
    )
