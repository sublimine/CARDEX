"""Router block — domain_map, circuit breaker, escalator, WAF classifier."""
from __future__ import annotations

import time

import pytest

from scrapers.engine.router import circuit, classifier, domain_map, escalator
from scrapers.engine.router.circuit import CircuitState
from scrapers.engine.router.domain_map import PortalSpec, Tier, WAF

_AS24_DE = "autoscout24.de"


# --------------------------------------------------------------------------- #
# domain_map.get — pattern matching
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_get_exact_match():
    spec = domain_map.get("coches.net")
    assert spec is not None
    assert spec.tier is Tier.T1
    assert spec.can_escalate_to is Tier.T2


@pytest.mark.unit
def test_get_tld_wildcard_matches_every_country():
    for host in ("autoscout24.de", "autoscout24.es", "autoscout24.fr", "autoscout24.nl"):
        spec = domain_map.get(host)
        assert spec is not None, host
        assert spec.tier is Tier.T2
        assert spec.waf is WAF.AKAMAI_V3


@pytest.mark.unit
def test_get_allows_leading_subdomain():
    assert domain_map.get("www.mobile.de") is not None
    assert domain_map.get("www.autoscout24.de") is not None


@pytest.mark.unit
def test_get_first_match_wins_respects_registry_order(monkeypatch):
    # When a host matches multiple patterns, the earliest REGISTRY entry wins.
    first = PortalSpec("dup.example", Tier.T1, WAF.NONE)
    second = PortalSpec("dup.example", Tier.T3, WAF.DATADOME)
    monkeypatch.setattr(domain_map, "REGISTRY", [first, second])
    assert domain_map.get("dup.example") is first


@pytest.mark.unit
def test_get_unknown_domain_is_none():
    assert domain_map.get("some-random-dealer.example") is None


# --------------------------------------------------------------------------- #
# domain_map.effective_tier — escalation walk
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_effective_tier_baseline_when_all_closed():
    assert domain_map.effective_tier(_AS24_DE, {}) is Tier.T2


@pytest.mark.unit
def test_effective_tier_skips_open_tier_up_to_ceiling():
    state = {(_AS24_DE, "T2"): "open"}
    assert domain_map.effective_tier(_AS24_DE, state) is Tier.T3


@pytest.mark.unit
def test_effective_tier_bounded_by_ceiling():
    # coches.net ceiling is T2; even with T1 and T2 open it cannot exceed T2.
    state = {("coches.net", "T1"): "open", ("coches.net", "T2"): "open"}
    assert domain_map.effective_tier("coches.net", state) is Tier.T2


@pytest.mark.unit
def test_effective_tier_no_escalation_config_stays_baseline():
    # heycar.com is T2 with no can_escalate_to → ceiling == baseline.
    state = {("heycar.com", "T2"): "open"}
    assert domain_map.effective_tier("heycar.com", state) is Tier.T2


@pytest.mark.unit
def test_effective_tier_unknown_domain_defaults_t1():
    assert domain_map.effective_tier("unknown.example", {}) is Tier.T1


@pytest.mark.unit
def test_effective_tier_accepts_tier_enum_keys():
    state = {(_AS24_DE, Tier.T2): "open"}
    assert domain_map.effective_tier(_AS24_DE, state) is Tier.T3


# --------------------------------------------------------------------------- #
# circuit breaker — state machine
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_circuit_starts_closed(conn):
    assert circuit.get_state(conn, "d.com", "T1") is CircuitState.CLOSED
    assert circuit.is_open(conn, "d.com", "T1") is False


@pytest.mark.unit
def test_three_failures_in_window_open(conn):
    # Anchor to wall-clock now: is_open() reads time.time(), so opened_at must be
    # recent for the breaker to still read OPEN (not aged into HALF_OPEN).
    base = int(time.time())
    circuit.record_failure(conn, "d.com", "T1", now=base)
    circuit.record_failure(conn, "d.com", "T1", now=base + 10)
    state = circuit.record_failure(conn, "d.com", "T1", now=base + 20)
    assert state is CircuitState.OPEN
    assert circuit.is_open(conn, "d.com", "T1") is True


@pytest.mark.unit
def test_failures_outside_window_do_not_accumulate(conn):
    circuit.record_failure(conn, "d.com", "T1", now=100)
    circuit.record_failure(conn, "d.com", "T1", now=200)  # >60s later → resets to 1
    state = circuit.record_failure(conn, "d.com", "T1", now=205)
    assert state is CircuitState.CLOSED  # only 2 within the latest window


@pytest.mark.unit
def test_get_state_is_read_only(conn):
    circuit.record_failure(conn, "d.com", "T1", now=100)
    before = conn.execute(
        "SELECT fail_count FROM domain_tier_state WHERE domain='d.com' AND tier='T1'"
    ).fetchone()["fail_count"]
    circuit.get_state(conn, "d.com", "T1")
    after = conn.execute(
        "SELECT fail_count FROM domain_tier_state WHERE domain='d.com' AND tier='T1'"
    ).fetchone()["fail_count"]
    assert before == after == 1


@pytest.mark.unit
def test_open_transitions_to_half_open_after_duration(conn):
    for t in (100, 110, 120):
        circuit.record_failure(conn, "d.com", "T1", now=t)
    # Age the open window past the 120s threshold relative to wall-clock now.
    conn.execute(
        "UPDATE domain_tier_state SET opened_at=? WHERE domain='d.com' AND tier='T1'",
        (int(time.time()) - 200,),
    )
    assert circuit.get_state(conn, "d.com", "T1") is CircuitState.HALF_OPEN


@pytest.mark.unit
def test_half_open_success_closes(conn):
    for t in (100, 110, 120):
        circuit.record_failure(conn, "d.com", "T1", now=t)
    # half-open window: now is 200s past opened_at.
    state = circuit.record_success(conn, "d.com", "T1", now=320)
    assert state is CircuitState.CLOSED
    row = conn.execute(
        "SELECT fail_count, opened_at FROM domain_tier_state "
        "WHERE domain='d.com' AND tier='T1'"
    ).fetchone()
    assert row["fail_count"] == 0
    assert row["opened_at"] is None


@pytest.mark.unit
def test_half_open_failure_reopens(conn):
    for t in (100, 110, 120):
        circuit.record_failure(conn, "d.com", "T1", now=t)
    state = circuit.record_failure(conn, "d.com", "T1", now=320)  # failed probe
    assert state is CircuitState.OPEN
    row = conn.execute(
        "SELECT opened_at FROM domain_tier_state WHERE domain='d.com' AND tier='T1'"
    ).fetchone()
    assert row["opened_at"] == 320  # window restarted at the probe failure


@pytest.mark.unit
def test_success_inside_open_window_keeps_open(conn):
    for t in (100, 110, 120):
        circuit.record_failure(conn, "d.com", "T1", now=t)
    state = circuit.record_success(conn, "d.com", "T1", now=130)  # still inside 120s
    assert state is CircuitState.OPEN


@pytest.mark.unit
def test_force_open_opens_immediately(conn):
    base = int(time.time())
    circuit.force_open(conn, "d.com", "T2", now=base)
    assert circuit.is_open(conn, "d.com", "T2") is True
    row = conn.execute(
        "SELECT opened_at FROM domain_tier_state WHERE domain='d.com' AND tier='T2'"
    ).fetchone()
    assert row["opened_at"] == base


# --------------------------------------------------------------------------- #
# escalator
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_next_tier_chain():
    assert escalator.next_tier(Tier.T0) is Tier.T1
    assert escalator.next_tier(Tier.T2) is Tier.T3
    assert escalator.next_tier(Tier.T3) is None


@pytest.mark.unit
def test_escalate_moves_up_and_persists(conn):
    nxt = escalator.escalate(conn, _AS24_DE, Tier.T2)
    assert nxt is Tier.T3
    # from_tier circuit is now OPEN and effective_tier cached.
    assert circuit.is_open(conn, _AS24_DE, "T2") is True
    row = conn.execute(
        "SELECT effective_tier FROM domain_tier_state WHERE domain=? AND tier='T2'",
        (_AS24_DE,),
    ).fetchone()
    assert row["effective_tier"] == "T3"


@pytest.mark.unit
def test_escalate_at_ceiling_returns_none(conn):
    # coches.net ceiling is T2 → escalating from T2 is refused.
    assert escalator.escalate(conn, "coches.net", Tier.T2) is None


@pytest.mark.unit
def test_escalate_from_t3_returns_none(conn):
    assert escalator.escalate(conn, "leboncoin.fr", Tier.T3) is None


@pytest.mark.unit
def test_get_effective_tier_reflects_escalation(conn):
    assert escalator.get_effective_tier(conn, _AS24_DE) is Tier.T2
    escalator.escalate(conn, _AS24_DE, Tier.T2)
    # Live recompute from the (now OPEN) circuit snapshot agrees with the cache.
    assert escalator.get_effective_tier(conn, _AS24_DE) is Tier.T3


@pytest.mark.unit
def test_get_effective_tier_deescalates_on_recovery(conn):
    escalator.escalate(conn, _AS24_DE, Tier.T2)
    assert escalator.get_effective_tier(conn, _AS24_DE) is Tier.T3
    # Half-open probe on T2 succeeds → breaker closes → tier falls back to T2.
    conn.execute(
        "UPDATE domain_tier_state SET opened_at=? WHERE domain=? AND tier='T2'",
        (int(time.time()) - 200, _AS24_DE),
    )
    circuit.record_success(conn, _AS24_DE, "T2")
    assert escalator.get_effective_tier(conn, _AS24_DE) is Tier.T2


# --------------------------------------------------------------------------- #
# classifier.classify_signals — pure WAF/tier decision
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_classify_datadome_header_is_t3():
    waf, tier = classifier.classify_signals(403, {"x-datadome": "protected"}, "")
    assert (waf, tier) == (WAF.DATADOME, Tier.T3)


@pytest.mark.unit
def test_classify_datadome_cookie_is_t3():
    headers = {"set-cookie": "datadome=abc123; Path=/; Secure"}
    waf, tier = classifier.classify_signals(200, headers, "<html></html>")
    assert (waf, tier) == (WAF.DATADOME, Tier.T3)


@pytest.mark.unit
def test_classify_perimeterx_is_t3():
    headers = {"set-cookie": "_pxhd=xyz; Path=/"}
    waf, tier = classifier.classify_signals(403, headers, "")
    assert (waf, tier) == (WAF.PERIMETER_X, Tier.T3)


@pytest.mark.unit
def test_classify_akamai_is_t2():
    headers = {"set-cookie": "ak_bmsc=token; Path=/", "cf-ray": "ignored"}
    waf, tier = classifier.classify_signals(200, headers, "")
    # Akamai outranks a co-present Cloudflare edge marker.
    assert (waf, tier) == (WAF.AKAMAI_V3, Tier.T2)


@pytest.mark.unit
def test_classify_cf_challenge_body_is_t2():
    waf, tier = classifier.classify_signals(
        503, {"cf-ray": "7a1b"}, "<title>Just a moment...</title>"
    )
    assert (waf, tier) == (WAF.CF_PRO, Tier.T2)


@pytest.mark.unit
def test_classify_cf_passive_200_is_t1():
    waf, tier = classifier.classify_signals(
        200, {"cf-ray": "7a1b", "server": "cloudflare"}, "<html>cars</html>"
    )
    assert (waf, tier) == (WAF.CF_FREE, Tier.T1)


@pytest.mark.unit
def test_classify_cf_edge_with_block_status_is_t2():
    waf, tier = classifier.classify_signals(403, {"server": "cloudflare"}, "")
    assert (waf, tier) == (WAF.CF_PRO, Tier.T2)


@pytest.mark.unit
def test_classify_unidentified_block_is_conservative_t2():
    waf, tier = classifier.classify_signals(403, {"server": "nginx"}, "forbidden")
    assert (waf, tier) == (WAF.UNKNOWN, Tier.T2)


@pytest.mark.unit
def test_classify_clean_200_is_t1():
    waf, tier = classifier.classify_signals(200, {"server": "nginx"}, "<html>ok</html>")
    assert (waf, tier) == (WAF.NONE, Tier.T1)


# --------------------------------------------------------------------------- #
# classifier persistence — persist / is_stale
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_persist_writes_classification(conn):
    spec = PortalSpec("newdealer.de", Tier.T2, WAF.CF_PRO)
    classifier.persist(conn, spec)
    row = conn.execute(
        "SELECT waf, tier, effective_tier, verified_at FROM domain_tier_state "
        "WHERE domain='newdealer.de'"
    ).fetchone()
    assert row["waf"] == "cf_pro"
    assert row["tier"] == "T2"
    assert row["effective_tier"] == "T2"
    assert row["verified_at"] is not None


@pytest.mark.unit
def test_persist_is_idempotent_upsert(conn):
    classifier.persist(conn, PortalSpec("d.de", Tier.T1, WAF.NONE))
    classifier.persist(conn, PortalSpec("d.de", Tier.T1, WAF.CF_PRO))
    rows = conn.execute(
        "SELECT waf FROM domain_tier_state WHERE domain='d.de'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["waf"] == "cf_pro"


@pytest.mark.unit
def test_is_stale_true_when_never_classified(conn):
    assert classifier.is_stale(conn, "never.de") is True


@pytest.mark.unit
def test_is_stale_false_right_after_persist(conn):
    classifier.persist(conn, PortalSpec("fresh.de", Tier.T1, WAF.NONE))
    assert classifier.is_stale(conn, "fresh.de") is False


@pytest.mark.unit
def test_is_stale_true_for_old_verification(conn):
    classifier.persist(conn, PortalSpec("old.de", Tier.T1, WAF.NONE))
    conn.execute(
        "UPDATE domain_tier_state SET verified_at=? WHERE domain='old.de'",
        (int(time.time()) - 8 * 86_400,),
    )
    assert classifier.is_stale(conn, "old.de", max_age_days=7) is True


@pytest.mark.unit
def test_is_stale_ignores_circuit_rows_without_verified_at(conn):
    # A circuit-breaker failure writes a row but never sets verified_at.
    circuit.record_failure(conn, "mixed.de", "T1", now=int(time.time()))
    assert classifier.is_stale(conn, "mixed.de") is True  # still unclassified
    classifier.persist(conn, PortalSpec("mixed.de", Tier.T2, WAF.CF_PRO))
    assert classifier.is_stale(conn, "mixed.de") is False
