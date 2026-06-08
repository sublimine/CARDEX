"""FR proxy resolver — pure helpers: city derivation + proxy-pool rotation (no network)."""
from __future__ import annotations

import pytest

from scrapers.discovery.domain_resolution.fr_resolver import derive_city
from scrapers.discovery.domain_resolution.proxy_pool import Proxy, RotatingPool


# ── derive_city (FR city is an INSEE code; real city is after the postcode) ──────
@pytest.mark.unit
def test_derive_city_from_postcode_in_address():
    assert derive_city("1 RPT DU 14 JUILLET 1789 95500 GONESSE", "95500", "95277") == "GONESSE"
    assert derive_city("Rue Saint-Pierre, 25, 60120, Esquennoy", "60120", "60123") == "Esquennoy"
    assert derive_city("Avenue du Poteau, 2005, 60300, Senlis", "60300", "60111") == "Senlis"


@pytest.mark.unit
def test_derive_city_drops_trailing_country():
    assert derive_city("FREIMATTE 25 77971 KIPPENHEIM ALLEMAGNE", "77971", "") == "KIPPENHEIM"


@pytest.mark.unit
def test_derive_city_falls_back_or_empty():
    # no postcode in address, INSEE-code city → unusable → ""
    assert derive_city("Rue Alfred Kastler", "", "95277") == ""
    assert derive_city("Rue du Haut, 24", None, "12345") == ""
    # non-numeric city field is usable as a fallback
    assert derive_city("Somewhere", "", "Lyon") == "Lyon"


# ── RotatingPool (round-robin + mark_dead), no network ──────────────────────────
@pytest.mark.unit
def test_rotating_pool_round_robin_and_mark_dead():
    pool = RotatingPool(target="x", floor=2)
    pool._live = [Proxy("http", "1.1.1.1:80"), Proxy("http", "2.2.2.2:80"), Proxy("http", "3.3.3.3:80")]
    got = [pool.get().addr for _ in range(4)]
    assert got == ["1.1.1.1:80", "2.2.2.2:80", "3.3.3.3:80", "1.1.1.1:80"]   # wraps
    pool.mark_dead(pool._live[1])                                            # drop 2.2.2.2
    assert {p.addr for p in pool._live} == {"1.1.1.1:80", "3.3.3.3:80"}
    assert pool.size == 2


@pytest.mark.unit
def test_rotating_pool_empty_get_is_none():
    pool = RotatingPool(target="x")
    assert pool.get() is None and pool.size == 0


@pytest.mark.unit
def test_proxy_url_scheme():
    assert Proxy("socks5", "9.9.9.9:1080").url == "socks5://9.9.9.9:1080"
    assert Proxy("http", "8.8.8.8:3128").url == "http://8.8.8.8:3128"
