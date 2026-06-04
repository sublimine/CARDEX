"""
CARDEX intelligence — anti-adversary detectors (SCRAPING_ENGINE.md §D).

Three independent detectors, each a pure function (or a thin DB writer) so they
are unit-testable without a live network or browser — the decoupling the previous
monolith lacked:

    waf      HTTP signals → WafVerdict     (D1: classify a new domain's anti-bot)
    schema   raw fields  → DriftResult     (D2: detect a portal's extraction-schema change)
    poison   HTML        → PoisonVerdict    (D3: Cloudflare AI-Labyrinth honeypot detection)

`poison.detect` is the single implementation of the poison signals; pipeline
quality GATE 2 imports it rather than re-deriving the logic (one source of truth).
The import direction is intelligence → pipeline.parse (never the reverse), so no
cycle: parse depends on nothing in this package.
"""
from __future__ import annotations

from scrapers.intelligence.poison import (
    POISON_THRESHOLD,
    PoisonVerdict,
    body_hash,
    detect,
)
from scrapers.intelligence.schema import DriftResult, check_drift, schema_fingerprint
from scrapers.intelligence.waf import WafVendor, WafVerdict, classify

__all__ = [
    "PoisonVerdict",
    "detect",
    "body_hash",
    "POISON_THRESHOLD",
    "WafVendor",
    "WafVerdict",
    "classify",
    "DriftResult",
    "check_drift",
    "schema_fingerprint",
]
