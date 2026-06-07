"""
Dealer auto-remediation (frente C, point 5) — close the loop when a dealer drifts.

The drift gate (point 4, ``intelligence.drift_gate``, reused by the harvester) raises
a by-source alert when a dealer's harvest collapses — almost always because the site
changed (a redesign, a CMS swap, a static→SPA migration) and the saved recipe no
longer matches. Remediation is the response:

    drift alert  →  RE-DETECT the site's CURRENT type  →  REGENERATE the config
                 →  REVALIDATE by re-harvesting a sample  →  recovered? resume : escalate

Because detection, config generation and the seam are all already built, this is a
WORKING loop, not a stub: ``remediate`` re-probes the live site (static first, then
render), writes a fresh recipe with a bumped ``version`` (the JSON store + git give
the audit trail), and re-runs a limited sample through the seam to confirm inventory
flows again. A dealer that yields nothing even after re-detection is escalated
(``recovered=False``) rather than silently retried forever.
"""
from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field

from scrapers.dealer_scraping.detector import build_config, detect_web_type
from scrapers.dealer_scraping.harvester import Purger, SeamRunner, harvest_dealer
from scrapers.intelligence import drift_gate
from scrapers.pipeline.generic_extractor import Fetcher
from scrapers.portals import config as portal_config
from scrapers.portals.config import ExtractionConfig

log = logging.getLogger(__name__)


@dataclass
class RemediationResult:
    """Outcome of one remediation attempt for a drifted dealer."""

    domain: str
    country: str
    old_strategy: str | None
    new_strategy: str | None
    strategy_changed: bool
    version: int
    recovered: bool
    persisted: int
    notes: tuple[str, ...] = field(default_factory=tuple)


def needs_remediation(cfg: ExtractionConfig, current_volume: int) -> bool:
    """True when a harvest's volume breaches the source's drift floor (by-source alert)."""
    return not drift_gate.evaluate_volume(cfg, current_volume).ok


def make_remediator(
    *,
    static_fetcher: Fetcher,
    e07_fetcher: Fetcher | None,
    seam_runner: SeamRunner,
    purger: Purger,
    limit: int = 12,
    save: bool = True,
):
    """
    Bind ``remediate`` into the ``(domain, country) -> RemediationResult`` callback the
    harvester expects, sharing the batch's fetchers/seam/purger. Pass the result as
    ``harvest_dealer(..., remediator=make_remediator(...))`` so a tripped drift gate
    auto-repairs the dealer in-flow.
    """
    async def _remediator(domain: str, country: str) -> RemediationResult:
        return await remediate(
            domain, country, static_fetcher=static_fetcher, e07_fetcher=e07_fetcher,
            seam_runner=seam_runner, purger=purger, limit=limit, save=save,
        )

    return _remediator


async def remediate(
    domain: str,
    country: str,
    *,
    static_fetcher: Fetcher,
    e07_fetcher: Fetcher | None,
    seam_runner: SeamRunner,
    purger: Purger,
    limit: int = 12,
    save: bool = True,
) -> RemediationResult:
    """
    Re-detect a drifted dealer, regenerate its (versioned) recipe, and revalidate.

    Static probe first, render only if needed (same cost discipline as detection).
    A new recipe is written with ``version = old + 1`` (or 1 when there was none),
    preserving the strategy-change record. Revalidation re-harvests a limited sample
    through the seam; ``recovered`` is True only when that sample actually persists
    inventory. Never raises for an ordinary failure.
    """
    country = (country or "").upper()[:2]
    old = portal_config.load(domain)
    old_strategy = old.strategy if old else None
    next_version = (old.version + 1) if old else 1

    # 1. RE-DETECT current type (force a live re-probe, ignore the stale recipe).
    detection = await detect_web_type(domain, country=country, static_fetcher=static_fetcher, e07_fetcher=None)
    if not detection.ok and e07_fetcher is not None:
        detection = await detect_web_type(
            domain, country=country, static_fetcher=static_fetcher, e07_fetcher=e07_fetcher
        )

    new_cfg = build_config(detection)
    if new_cfg is None:
        # Site yields nothing even after re-detection → escalate, do not loop.
        return RemediationResult(
            domain=domain, country=country, old_strategy=old_strategy, new_strategy=None,
            strategy_changed=old_strategy is not None, version=next_version,
            recovered=False, persisted=0, notes=detection.notes or ("still_no_inventory",),
        )

    # 2. REGENERATE the config with a bumped version (audit trail in git).
    new_cfg = dataclasses.replace(new_cfg, version=next_version)
    if save:
        portal_config.save(new_cfg, kind="dealer")

    # 3. REVALIDATE: re-harvest a sample with the fresh recipe. harvest_dealer resolves
    #    the recipe via portal_config.load (read-your-own-write), so a live revalidation
    #    requires the new config to have been persisted (save=True). In a dry run we
    #    report the regenerated recipe without claiming recovery.
    if not save:
        return RemediationResult(
            domain=domain, country=country, old_strategy=old_strategy,
            new_strategy=new_cfg.strategy, strategy_changed=(old_strategy != new_cfg.strategy),
            version=next_version, recovered=False, persisted=0, notes=("regenerated_dry_run",),
        )
    result = await harvest_dealer(
        domain, country, static_fetcher=static_fetcher, e07_fetcher=e07_fetcher,
        seam_runner=seam_runner, purger=purger, limit=limit, save_config=False, purge=True,
    )

    return RemediationResult(
        domain=domain, country=country, old_strategy=old_strategy,
        new_strategy=new_cfg.strategy, strategy_changed=(old_strategy != new_cfg.strategy),
        version=next_version, recovered=result.persisted > 0, persisted=result.persisted,
        notes=("revalidated",) if result.persisted > 0 else ("regenerated_but_empty",),
    )
