"""
Drift gate — the anti-breakage hook a harvest passes through before it's trusted.

This composes the two halves of "is this portal still healthy?" into one verdict
per source, building on what already exists rather than reinventing:

  * SCHEMA drift   — does the *shape* of extracted fields still match the baseline?
                     Delegated to ``intelligence.schema.check_drift`` (the verified
                     D2 detector over ``schema_registry``). A portal redesign that
                     shifts which fields the parser fills trips this.
  * VOLUME drift   — did the cycle yield at least ``drift_baseline.expected_min_volume``?
                     A silent block / broken selector that returns far fewer (or zero)
                     listings trips this. (Complements P0-1's harvest-0 EMPTY_SUSPECT
                     with a per-source *expected* floor, not just "> 0".)
  * FIELD drift    — do at least ``min_nonnull_ratio`` of records carry every
                     ``required_field``? A layout change that drops price/year while
                     keeping the page parseable trips this — the "200-OK but empty"
                     class the null-field tracker watches, here pinned to a contract.

The verdict (``DriftReport``) names exactly which dimension broke, so the alert is
*by source and by cause* and the repair is a single edit to that source's
``configs/portals/<source>.json``. This is the seed: when a portal changes its HTML,
the gate fails, the operator is told which source and which dimension, and the fix
touches only that config.

``evaluate`` is the one call a harvest/verify path makes; ``HarvestStats`` is the
cheap roll-up a caller already has (count + per-field non-null tally + one sample
field-set for the fingerprint). Pure except for the schema_registry read/write,
which is injected as a sqlite connection (None → skip schema dimension, test-friendly).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from scrapers.intelligence import schema as schema_drift
from scrapers.portals.config import ExtractionConfig


@dataclass(frozen=True)
class HarvestStats:
    """Cheap roll-up of one harvest cycle, for the drift gate."""

    volume: int                                   # records that reached L2 (or deep-links)
    field_nonnull: Mapping[str, int]              # required_field -> count present
    sample_raw_fields: Mapping[str, Any]          # one record's extracted field-set (for schema_fp)


@dataclass(frozen=True)
class DriftReport:
    """Per-source drift verdict. ``alert`` is True when ANY dimension breaks."""

    source_key: str
    ok: bool
    volume_ok: bool
    fields_ok: bool
    schema_changed: bool
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def alert(self) -> bool:
        return not self.ok

    def reason(self) -> str:
        """Human one-liner naming the broken dimension(s) for the alert."""
        if self.ok:
            return "ok"
        broken = []
        if not self.volume_ok:
            broken.append(f"volume({self.details.get('volume')}<{self.details.get('expected_min')})")
        if not self.fields_ok:
            broken.append(f"fields({','.join(self.details.get('weak_fields', []))})")
        if self.schema_changed:
            broken.append("schema_fp_changed")
        return "drift:" + "+".join(broken)


def _fields_ok(stats: HarvestStats, cfg: ExtractionConfig) -> tuple[bool, list[str]]:
    """True when every required field clears min_nonnull_ratio; else the weak fields."""
    base = cfg.drift_baseline
    if stats.volume <= 0:
        return False, list(base.required_fields)
    weak: list[str] = []
    for f in base.required_fields:
        ratio = stats.field_nonnull.get(f, 0) / stats.volume
        if ratio < base.min_nonnull_ratio:
            weak.append(f)
    return (not weak), weak


def evaluate(
    cfg: ExtractionConfig,
    stats: HarvestStats,
    *,
    conn: Any | None = None,
) -> DriftReport:
    """
    Run the three drift dimensions for one source and return a single verdict.

    ``conn`` is a sqlite connection to engine.db for the schema_registry baseline;
    pass None to skip the schema dimension (e.g. pure unit tests). The caller acts
    on ``report.alert`` (pause source, DLQ pending, notify) — the repair is editing
    ``cfg``'s JSON.
    """
    base = cfg.drift_baseline

    volume_ok = stats.volume >= base.expected_min_volume
    fields_ok, weak = _fields_ok(stats, cfg)

    schema_changed = False
    old_fp = new_fp = None
    if conn is not None and stats.sample_raw_fields:
        new_fp = schema_drift.schema_fingerprint(
            stats.sample_raw_fields, extraction_method=base.extraction_method
        )
        result = schema_drift.check_drift(conn, cfg.source_key, new_fp, base.extraction_method)
        schema_changed = result.changed
        old_fp = result.old_fp

    ok = volume_ok and fields_ok and not schema_changed
    return DriftReport(
        source_key=cfg.source_key,
        ok=ok,
        volume_ok=volume_ok,
        fields_ok=fields_ok,
        schema_changed=schema_changed,
        details={
            "volume": stats.volume,
            "expected_min": base.expected_min_volume,
            "weak_fields": weak,
            "old_fp": old_fp,
            "new_fp": new_fp,
        },
    )


def stats_from_records(
    records: Sequence[Mapping[str, Any]],
    required_fields: Sequence[str],
) -> HarvestStats:
    """
    Build HarvestStats from a list of extracted records (dicts).

    A convenience for callers that have the records in hand (the verify path):
    counts non-null per required field and takes the first record's key-set as the
    schema-fingerprint sample.
    """
    nonnull: dict[str, int] = {f: 0 for f in required_fields}
    for rec in records:
        for f in required_fields:
            v = rec.get(f)
            if v not in (None, "", [], (), {}):
                nonnull[f] += 1
    sample = dict(records[0]) if records else {}
    return HarvestStats(volume=len(records), field_nonnull=nonnull, sample_raw_fields=sample)
