"""
Unit tests for the osm_nametail signal/noise filter.

Run: python -m pytest scrapers/discovery/sources/test_osm_nametail_filter.py -v
Or:  python scrapers/discovery/sources/test_osm_nametail_filter.py
"""
from __future__ import annotations

import sys
import os

# Allow running from repo root without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from scrapers.discovery.sources.osm_nametail import (
    _passes_filter,
    _to_candidate,
    _build_alternation,
    _cells,
)


# ---------------------------------------------------------------------------
# Helper to build a minimal OSM element dict
# ---------------------------------------------------------------------------

def _el(name: str, lat: float = 48.0, lon: float = 8.0, etype: str = "node", **tags) -> dict:
    return {
        "type": etype,
        "id":   999999,
        "lat":  lat,
        "lon":  lon,
        "tags": {"name": name, **tags},
    }


def _way_el(name: str, clat: float = 48.0, clon: float = 8.0, **tags) -> dict:
    return {
        "type":   "way",
        "id":     888888,
        "center": {"lat": clat, "lon": clon},
        "tags":   {"name": name, **tags},
    }


# ---------------------------------------------------------------------------
# PASS cases — should survive the filter
# ---------------------------------------------------------------------------

class TestPassCases:
    def test_autohaus_with_website(self):
        """Classic Autohaus with website — strong term + website → must pass."""
        tags = {"website": "https://autohaus-mueller.de"}
        assert _passes_filter("Autohaus Müller", tags, "DE") is True

    def test_autohaus_strong_term_no_website(self):
        """Strong term 'autohaus' — no website needed."""
        assert _passes_filter("Autohaus Schmidt", {}, "DE") is True

    def test_concessionnaire_strong_term_fr(self):
        """'concessionnaire' is a strong term for FR."""
        assert _passes_filter("Concessionnaire Peugeot Lyon", {}, "FR") is True

    def test_autobedrijf_strong_term_nl(self):
        """'autobedrijf' is a strong term for NL."""
        assert _passes_filter("Autobedrijf Janssen", {}, "NL") is True

    def test_garagebedrijf_strong_term_nl(self):
        """'garagebedrijf' is a strong term for NL."""
        assert _passes_filter("Garagebedrijf Van Dijk", {}, "NL") is True

    def test_concesionario_strong_term_es(self):
        """'concesionario' is a strong term for ES."""
        assert _passes_filter("Concesionario Toyota Madrid", {}, "ES") is True

    def test_carrozzeria_strong_term_ch_it(self):
        """'carrozzeria' is a strong term for CH (Italian region)."""
        assert _passes_filter("Carrozzeria Rossi", {}, "CH") is True

    def test_garage_with_shop_car(self):
        """Generic 'garage' alone is weak, but shop=car tag makes it pass."""
        assert _passes_filter("Garage Martin", {"shop": "car"}, "FR") is True

    def test_garage_with_website(self):
        """Generic 'garage' alone is weak, but website makes it pass."""
        assert _passes_filter("Garage Dupont", {"website": "https://garage-dupont.fr"}, "FR") is True

    def test_kfz_strong_de(self):
        """'kfz' is a strong term for DE."""
        assert _passes_filter("KFZ Werkstatt Berlin", {}, "DE") is True

    def test_autosalone_ch_strong(self):
        """'autosalone' is a strong CH/IT term."""
        assert _passes_filter("Autosalone Ticino", {}, "CH") is True

    def test_to_candidate_pass(self):
        """_to_candidate returns a non-None dict for a clear Autohaus."""
        el = _el("Autohaus Testmann", lat=48.5, lon=9.0, website="https://test.de")
        cand = _to_candidate(el, "DE")
        assert cand is not None
        assert cand["name"] == "Autohaus Testmann"
        assert cand["domain"] == "test.de"
        assert cand["registry_id"] == "node/999999"
        assert cand["source"] == "osm_nametail"

    def test_to_candidate_way(self):
        """_to_candidate works for way elements (uses center lat/lon)."""
        el = _way_el("Autobedrijf Test NL", clat=52.0, clon=4.5)
        cand = _to_candidate(el, "NL")
        assert cand is not None
        assert cand["lat"] == 52.0
        assert cand["lng"] == 4.5


# ---------------------------------------------------------------------------
# REJECT cases — noise that must be filtered out
# ---------------------------------------------------------------------------

class TestRejectCases:
    def test_restaurant_le_garage_no_signal(self):
        """'Le Garage' restaurant — generic term 'garage', no website, no car tag."""
        # amenity=restaurant is NOT in _AUTO_TAG_VALUES
        assert _passes_filter("Restaurant Le Garage", {"amenity": "restaurant"}, "FR") is False

    def test_bar_le_garage(self):
        """Bar named 'Le Garage' — no automotive signal."""
        assert _passes_filter("Bar Le Garage", {}, "FR") is False

    def test_autoescuela_weak_no_signal(self):
        """'autoescuela' doesn't appear in ES terms, so it won't even reach filter.
        Here we test a weak term like 'taller' without extra signal."""
        # taller (workshop) is an ES term but it's generic — no website, no car tag
        # The filter should reject it (it IS in terms_for('ES'), so overpass would return it,
        # but the filter requires extra signal since 'taller' is not a strong term).
        assert _passes_filter("Taller de bordados", {}, "ES") is False

    def test_garage_no_signal_de(self):
        """In DE, 'garage' appears in CH terms but NOT in DE terms — irrelevant.
        But even if a name matches via alternation, filter must check country terms."""
        # This tests the case: name matches but no website/auto-tag/strong-term for DE
        # 'garage' is not in DE terms, so terms_for('DE') won't include it.
        assert _passes_filter("Garage am See", {}, "DE") is False

    def test_to_candidate_returns_none_for_noise(self):
        """_to_candidate returns None for a restaurant named 'Le Garage'."""
        el = _el("Restaurant Le Garage", lat=48.8, lon=2.3, amenity="restaurant")
        cand = _to_candidate(el, "FR")
        assert cand is None

    def test_occasions_weak_without_signal_be(self):
        """'occasions' alone in BE is weak (appears in secondhand shops, flea markets)."""
        # 'occasions' is NOT in _STRONG_TERMS → needs website or car tag
        assert _passes_filter("Marché aux Occasions", {}, "BE") is False

    def test_occasions_with_car_tag_be(self):
        """'occasions' with shop=car_dealer passes."""
        assert _passes_filter("Occasions Plus", {"shop": "car_dealer"}, "BE") is True


# ---------------------------------------------------------------------------
# Grid sanity tests
# ---------------------------------------------------------------------------

class TestGrid:
    def test_be_cell_count_reasonable(self):
        """Belgium with 0.3° step should produce ~30–60 cells."""
        n = sum(1 for _ in _cells("BE"))
        assert 20 <= n <= 100, f"BE cell count out of range: {n}"

    def test_de_more_cells_than_be(self):
        """Germany (large) should have more cells than Belgium (small)."""
        n_de = sum(1 for _ in _cells("DE"))
        n_be = sum(1 for _ in _cells("BE"))
        assert n_de > n_be

    def test_no_cell_exceeds_step(self):
        """All cells should be <= step size in both dimensions."""
        step = 0.3
        for s, w, n, e in _cells("BE"):
            assert n - s <= step + 1e-9
            assert e - w <= step + 1e-9


# ---------------------------------------------------------------------------
# Alternation sanity tests
# ---------------------------------------------------------------------------

class TestAlternation:
    def test_de_alternation_contains_autohaus(self):
        alt = _build_alternation("DE")
        assert "autohaus" in alt

    def test_fr_alternation_contains_concessionnaire(self):
        alt = _build_alternation("FR")
        assert "concessionnaire" in alt

    def test_ch_alternation_contains_italian(self):
        alt = _build_alternation("CH")
        assert "carrozzeria" in alt or "autosalone" in alt


# ---------------------------------------------------------------------------
# Standalone runner (no pytest required)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    suites = [TestPassCases, TestRejectCases, TestGrid, TestAlternation]
    passed = 0
    failed = 0
    for suite_cls in suites:
        suite = suite_cls()
        for method_name in [m for m in dir(suite_cls) if m.startswith("test_")]:
            method = getattr(suite, method_name)
            try:
                method()
                print(f"  PASS  {suite_cls.__name__}.{method_name}")
                passed += 1
            except Exception:
                print(f"  FAIL  {suite_cls.__name__}.{method_name}")
                traceback.print_exc()
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
