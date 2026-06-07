"""
Dealer config store — the auto-generated per-dealer recipe lives in a SEPARATE
versioned store (``configs/dealers/``) but resolves through the SAME ``config.load``
the seam uses, so ``enrich_worker`` routes a dealer's strategy with no seam change.

These cover the additive extension to ``scrapers/portals/config.py``:
  * dealer save/load round-trips through the dealer dir,
  * a curated portal recipe WINS over a dealer one for the same domain,
  * ``list_configs`` selects portal / dealer / all,
  * existing portal behaviour is untouched (covered by test_portal_config.py).
"""
from __future__ import annotations

import pytest

from scrapers.portals import config as cfgmod
from scrapers.portals.config import ExtractionConfig, DriftBaseline, Endpoints


def _dealer_cfg(domain: str, strategy: str = "sitemap_listing", country: str = "DE") -> ExtractionConfig:
    return ExtractionConfig(
        source_key=domain,
        country=country,
        strategy=strategy,
        endpoints=Endpoints(host=f"www.{domain}", sitemap_url=f"https://{domain}/sitemap.xml"),
        drift_baseline=DriftBaseline(expected_min_volume=5, required_fields=("make", "model", "year", "price")),
    )


@pytest.fixture()
def isolated_stores(tmp_path, monkeypatch):
    """Point both config stores at empty tmp dirs so tests never touch the repo."""
    portal_dir = tmp_path / "portals"
    dealer_dir = tmp_path / "dealers"
    portal_dir.mkdir()
    dealer_dir.mkdir()
    monkeypatch.setattr(cfgmod, "_CONFIG_DIR", portal_dir)
    monkeypatch.setattr(cfgmod, "_DEALER_DIR", dealer_dir)
    return portal_dir, dealer_dir


@pytest.mark.unit
def test_dealer_save_writes_to_dealer_dir(isolated_stores):
    portal_dir, dealer_dir = isolated_stores
    cfg = _dealer_cfg("autohaus-bahm.de")
    path = cfgmod.save(cfg, kind="dealer")
    assert path.parent == dealer_dir
    assert not (portal_dir / "autohaus-bahm.de.json").exists()
    assert path.exists()


@pytest.mark.unit
def test_load_resolves_dealer_config_for_the_seam(isolated_stores):
    cfg = _dealer_cfg("busato.fr", strategy="playwright_meta", country="FR")
    cfgmod.save(cfg, kind="dealer")
    # The seam calls plain load(domain) — it must find the dealer recipe.
    loaded = cfgmod.load("busato.fr")
    assert loaded is not None
    assert loaded.strategy == "playwright_meta"
    assert loaded.country == "FR"


@pytest.mark.unit
def test_curated_portal_wins_over_dealer_for_same_domain(isolated_stores):
    portal_dir, _ = isolated_stores
    domain = "overlap.de"
    cfgmod.save(_dealer_cfg(domain, strategy="playwright_meta"), kind="dealer")
    cfgmod.save(_dealer_cfg(domain, strategy="sitemap_listing"), kind="portal")
    # Both exist; load must return the curated portal recipe (precedence).
    assert cfgmod.load(domain).strategy == "sitemap_listing"


@pytest.mark.unit
def test_list_configs_kind_selection(isolated_stores):
    cfgmod.save(_dealer_cfg("d1.de"), kind="dealer")
    cfgmod.save(_dealer_cfg("d2.fr", country="FR"), kind="dealer")
    cfgmod.save(_dealer_cfg("p1.nl", country="NL"), kind="portal")
    assert cfgmod.list_configs("dealer") == ["d1.de", "d2.fr"]
    assert cfgmod.list_configs("portal") == ["p1.nl"]
    assert cfgmod.list_configs("all") == ["d1.de", "d2.fr", "p1.nl"]


@pytest.mark.unit
def test_missing_in_both_stores_returns_none(isolated_stores):
    assert cfgmod.load("nowhere.invalid") is None
