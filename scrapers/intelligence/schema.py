"""
Schema-drift detector (D2) — catch a portal silently changing its page structure.

A portal redesign or A/B test shifts which fields the parser can extract; left
unnoticed, the pipeline keeps ingesting half-empty records. SCRAPING_ENGINE.md §D2
fingerprints each portal's extraction schema and, when the fingerprint changes
from the stored baseline, signals an alert so the coordinator can pause the portal
and DLQ its pending work before bad data accumulates.

`schema_fingerprint` is pure (HTML-shape in, hash out). `check_drift` is the thin
DB writer over the `schema_registry` table: it owns first-observation insert,
unchanged-sample bookkeeping, and the change transition. The two are split so the
fingerprint can be unit-tested without a database.

Deviation from §D2's literal `hash(regex_pattern + extraction_method + sample_count)`:
the pipeline has no single "regex_pattern" — the *set of fields successfully
extracted* is the observable schema. We hash that key-set plus the extraction
method. `sample_count` is excluded from the fingerprint on purpose: folding a
monotonically rising counter into the hash would make every cycle look like drift.
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# Values that count as "field absent" — an empty extraction, not a real datum.
_EMPTY = (None, "", [], (), {})


@dataclass(frozen=True)
class DriftResult:
    """Outcome of one drift check. `changed` is True only on a real fingerprint shift."""

    portal: str
    changed: bool
    old_fp: str | None
    new_fp: str


def schema_fingerprint(raw_fields: Mapping[str, Any], *, extraction_method: str) -> str:
    """
    32-hex-char hash of the extracted-field shape for one portal.

    The fingerprint is over the *sorted set of present field names* joined with the
    extraction method. Field values are ignored — only which fields the parser could
    fill matters, so two listings of the same shape with different data agree.
    """
    present = sorted(k for k, v in raw_fields.items() if v not in _EMPTY)
    payload = "\x1f".join((extraction_method, *present))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def check_drift(
    conn: sqlite3.Connection,
    portal: str,
    new_fp: str,
    extraction_method: str,
    now: int | None = None,
) -> DriftResult:
    """
    Compare `new_fp` against the stored baseline and persist the outcome.

      first observation  → insert baseline, changed=False
      same fingerprint   → bump sample_count + verified_at, changed=False
      different finger­print → overwrite, set last_change_at, changed=True

    The caller acts on `changed` (pause portal, DLQ pending). Writes are wrapped in
    the connection's implicit transaction; `now` is injectable for deterministic tests.
    """
    ts = int(time.time()) if now is None else now
    row = conn.execute(
        "SELECT schema_fp FROM schema_registry WHERE portal = ?", (portal,)
    ).fetchone()

    if row is None:
        conn.execute(
            "INSERT INTO schema_registry "
            "(portal, schema_fp, extraction_method, sample_count, verified_at) "
            "VALUES (?, ?, ?, 1, ?)",
            (portal, new_fp, extraction_method, ts),
        )
        return DriftResult(portal=portal, changed=False, old_fp=None, new_fp=new_fp)

    old_fp = row["schema_fp"]
    if old_fp == new_fp:
        conn.execute(
            "UPDATE schema_registry "
            "SET sample_count = sample_count + 1, verified_at = ? WHERE portal = ?",
            (ts, portal),
        )
        return DriftResult(portal=portal, changed=False, old_fp=old_fp, new_fp=new_fp)

    conn.execute(
        "UPDATE schema_registry "
        "SET schema_fp = ?, extraction_method = ?, verified_at = ?, last_change_at = ? "
        "WHERE portal = ?",
        (new_fp, extraction_method, ts, ts, portal),
    )
    return DriftResult(portal=portal, changed=True, old_fp=old_fp, new_fp=new_fp)
