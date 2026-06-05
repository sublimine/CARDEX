"""
Direct-identity unit tests — the no-proxy path that unblocks T0/T1.

Covers the whole fix surface at the unit level (no curl_cffi / network):
  * profile.generate_direct        — coherent identity with empty proxy fields
  * direct.ensure_direct_identities — idempotent active/warmed provisioning
  * store.pick_for_portal(require_proxy) — T2/T3 reject direct identities
  * proxy.tiers.allows_direct/requires_proxy — the direct-vs-proxy policy
  * BasePortalScraper._direct_pace/_sleep — the direct rate-limit floor

The live, end-to-end proof (real curl_cffi session + marktplaats + PG) lives in
the bounded live demo, not here.
"""
from __future__ import annotations

import asyncio

import pytest

from scrapers.engine.identity import coherence, store
from scrapers.engine.identity.direct import (
    DEFAULT_PER_COUNTRY,
    ensure_direct_identities,
)
from scrapers.engine.identity.profile import (
    COUNTRY_TIMEZONES,
    IdentityStatus,
    ProxyTier,
    generate_direct,
)
from scrapers.engine.proxy import tiers
from scrapers.engine.router.domain_map import Tier
from scrapers.portals.marktplaats_nl import MarktplaatsNLScraper


# --------------------------------------------------------------------------- #
# profile.generate_direct
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_generate_direct_has_empty_proxy_and_direct_tier() -> None:
    idy = generate_direct("NL")
    assert idy.proxy_tier is ProxyTier.DIRECT
    assert idy.proxy_ip == ""
    assert idy.proxy_provider == "direct"
    assert idy.fingerprint is not None
    # webrtc_ip must mirror the (empty) proxy_ip so coherence holds.
    assert idy.fingerprint.webrtc_ip == ""


@pytest.mark.unit
def test_generate_direct_is_coherent() -> None:
    # A direct identity must still pass the coherence enforcer (UA↔OS↔TLS↔geo,
    # webrtc_ip == proxy_ip == "").
    coherence.validate_creation(generate_direct("DE"))


@pytest.mark.unit
def test_generate_direct_is_deterministic_by_id() -> None:
    iid = "33333333-3333-3333-3333-333333333333"
    a = generate_direct("FR", identity_id=iid)
    b = generate_direct("FR", identity_id=iid)
    assert a.fingerprint.user_agent == b.fingerprint.user_agent


@pytest.mark.unit
def test_direct_session_goes_direct() -> None:
    # tls.make_session sends proxies=None when proxy_ip is falsy — assert the
    # condition that selects the direct branch.
    assert generate_direct("CH").proxy_ip == ""


# --------------------------------------------------------------------------- #
# direct.ensure_direct_identities
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_ensure_creates_active_warmed_direct_identities(conn) -> None:
    created = ensure_direct_identities(conn)
    assert created == DEFAULT_PER_COUNTRY * len(COUNTRY_TIMEZONES)

    actives = store.list_by_status(conn, IdentityStatus.ACTIVE)
    assert len(actives) == created
    for idy in actives:
        assert idy.proxy_tier is ProxyTier.DIRECT
        assert idy.warming_done is True
        assert idy.trust_score >= 1.0
        assert idy.status is IdentityStatus.ACTIVE


@pytest.mark.unit
def test_ensure_is_idempotent(conn) -> None:
    first = ensure_direct_identities(conn)
    second = ensure_direct_identities(conn)
    assert first > 0
    assert second == 0  # nothing new on the second pass
    assert len(store.list_by_status(conn, IdentityStatus.ACTIVE)) == first


@pytest.mark.unit
def test_ensure_respects_per_country_and_countries(conn) -> None:
    created = ensure_direct_identities(conn, per_country=2, countries=["NL"])
    assert created == 2
    nl = store.list_by_status(conn, IdentityStatus.ACTIVE, country="NL")
    assert len(nl) == 2
    assert store.list_by_status(conn, IdentityStatus.ACTIVE, country="DE") == []


@pytest.mark.unit
def test_ensure_enables_pick_for_t0_portal(conn) -> None:
    ensure_direct_identities(conn, per_country=1, countries=["NL"])
    # A T0 portal (marktplaats.nl is NL) must now find an eligible identity.
    picked = store.pick_for_portal(conn, "NL", "marktplaats.nl")
    assert picked is not None
    assert picked.proxy_tier is ProxyTier.DIRECT


# --------------------------------------------------------------------------- #
# store.pick_for_portal — require_proxy gate
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_pick_require_proxy_excludes_direct_identities(conn) -> None:
    ensure_direct_identities(conn, per_country=1, countries=["DE"])
    # T0/T1 (require_proxy=False) see the direct identity...
    assert store.pick_for_portal(conn, "DE", "x.de", require_proxy=False) is not None
    # ...but T2/T3 (require_proxy=True) must not — no proxied identity exists.
    assert store.pick_for_portal(conn, "DE", "mobile.de", require_proxy=True) is None


@pytest.mark.unit
def test_pick_require_proxy_keeps_proxied_identities(conn, make_identity) -> None:
    proxied = make_identity(country="DE", tier=ProxyTier.ISP_STICKY)
    store.save(conn, proxied)
    conn.execute(
        "UPDATE identities SET status='active', warming_done=1, trust_score=1.0 WHERE id=?",
        (proxied.id,),
    )
    got = store.pick_for_portal(conn, "DE", "mobile.de", require_proxy=True)
    assert got is not None and got.proxy_tier is ProxyTier.ISP_STICKY


@pytest.mark.unit
def test_high_trust_direct_identity_is_not_premium(conn) -> None:
    # A direct identity that accrued trust >= 7.0 must NOT count as premium —
    # premium gates T3 dispatch, which a direct identity can never serve.
    ensure_direct_identities(conn, per_country=1, countries=["DE"])
    conn.execute("UPDATE identities SET trust_score=9.0 WHERE proxy_tier='direct'")
    assert store.premium_count(conn) == 0
    assert store.premium_count(conn, "DE") == 0


# --------------------------------------------------------------------------- #
# proxy.tiers — direct-vs-proxy policy
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_allows_direct_only_t0_t1() -> None:
    assert tiers.allows_direct(Tier.T0) is True
    assert tiers.allows_direct(Tier.T1) is True
    assert tiers.allows_direct(Tier.T2) is False
    assert tiers.allows_direct(Tier.T3) is False


@pytest.mark.unit
def test_requires_proxy_is_inverse_of_allows_direct() -> None:
    for t in Tier:
        assert tiers.requires_proxy(t) is (not tiers.allows_direct(t))


@pytest.mark.unit
def test_required_proxy_tier_fallback_map_unchanged() -> None:
    # The proxy-fallback map is untouched: it still answers ISP_STICKY for T0/T1.
    assert tiers.required_proxy_tier(Tier.T0) is ProxyTier.ISP_STICKY
    assert tiers.required_proxy_tier(Tier.T1) is ProxyTier.ISP_STICKY


# --------------------------------------------------------------------------- #
# BasePortalScraper — direct rate-limit floor
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_direct_pace_is_per_tier_for_direct_identity() -> None:
    scraper = MarktplaatsNLScraper()
    direct = generate_direct("NL")
    assert scraper._direct_pace(Tier.T0, direct) == 1.0   # 1 req/s
    assert scraper._direct_pace(Tier.T1, direct) == 2.0   # 0.5 req/s
    assert scraper._direct_pace(Tier.T2, direct) == 0.0   # not a direct tier


@pytest.mark.unit
def test_direct_pace_zero_for_proxied_identity(make_identity) -> None:
    scraper = MarktplaatsNLScraper()
    proxied = make_identity(country="NL", tier=ProxyTier.ISP_STICKY)
    assert scraper._direct_pace(Tier.T0, proxied) == 0.0


@pytest.mark.unit
def test_sleep_never_undercuts_the_direct_floor(monkeypatch) -> None:
    captured: list[float] = []

    async def fake_sleep(d: float) -> None:
        captured.append(d)

    monkeypatch.setattr("scrapers.portals.base.asyncio.sleep", fake_sleep)
    scraper = MarktplaatsNLScraper()  # SLEEP_JITTER default 0.4
    asyncio.run(scraper._sleep(1.0))   # T0 floor
    asyncio.run(scraper._sleep(2.0))   # T1 floor
    assert captured[0] >= 1.0 and captured[0] <= 1.0 + scraper.SLEEP_JITTER
    assert captured[1] >= 2.0 and captured[1] <= 2.0 + scraper.SLEEP_JITTER


@pytest.mark.unit
def test_sleep_uses_base_rhythm_without_pace(monkeypatch) -> None:
    captured: list[float] = []

    async def fake_sleep(d: float) -> None:
        captured.append(d)

    monkeypatch.setattr("scrapers.portals.base.asyncio.sleep", fake_sleep)
    scraper = MarktplaatsNLScraper()  # SLEEP_BASE 1.2 ± 0.4
    asyncio.run(scraper._sleep())  # pace defaults to 0.0
    assert scraper.SLEEP_BASE - scraper.SLEEP_JITTER <= captured[0] <= scraper.SLEEP_BASE + scraper.SLEEP_JITTER
