"""Monitoring block — Prometheus metrics round-trips, degraded wrappers, soft-block detectors."""
from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry

from scrapers.engine.monitoring import metrics, softblock
from scrapers.engine.monitoring.metrics import EngineMetrics
from scrapers.engine.monitoring.softblock import NullFieldTracker, ZeroUrlTracker


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def em() -> EngineMetrics:
    """An EngineMetrics scoped to an isolated registry — no global pollution."""
    return EngineMetrics(registry=CollectorRegistry())


def _val(em: EngineMetrics, name: str, labels: dict | None = None) -> float | None:
    return em.registry.get_sample_value(name, labels or {})


# --------------------------------------------------------------------------- #
# availability + construction
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_is_available_true_when_prometheus_installed() -> None:
    assert metrics.is_available() is True


@pytest.mark.unit
def test_engine_metrics_uses_provided_registry() -> None:
    reg = CollectorRegistry()
    em = EngineMetrics(registry=reg)
    assert em.registry is reg


@pytest.mark.unit
def test_engine_metrics_builds_default_registry_when_none() -> None:
    em = EngineMetrics()
    assert em.registry is not None


# --------------------------------------------------------------------------- #
# per portal + tier
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_record_request_increments_counter_and_histogram(em: EngineMetrics) -> None:
    em.record_request("autoscout24", "t1", 200, 0.42)
    labels = {"portal": "autoscout24", "tier": "t1", "status_code": "200"}
    assert _val(em, "scraper_requests_total", labels) == 1.0
    hist_labels = {"portal": "autoscout24", "tier": "t1"}
    assert _val(em, "scraper_request_duration_seconds_count", hist_labels) == 1.0
    assert _val(em, "scraper_request_duration_seconds_sum", hist_labels) == pytest.approx(0.42)


@pytest.mark.unit
def test_record_request_status_code_is_label(em: EngineMetrics) -> None:
    em.record_request("heycar", "t2", 403, 1.0)
    assert _val(em, "scraper_requests_total", {"portal": "heycar", "tier": "t2", "status_code": "403"}) == 1.0


@pytest.mark.unit
def test_record_urls_collected_accumulates(em: EngineMetrics) -> None:
    em.record_urls_collected("autoscout24", "DE", 20)
    em.record_urls_collected("autoscout24", "DE", 15)
    assert _val(em, "scraper_urls_collected_total", {"portal": "autoscout24", "country": "DE"}) == 35.0


@pytest.mark.unit
def test_record_urls_collected_zero_is_noop(em: EngineMetrics) -> None:
    em.record_urls_collected("autoscout24", "DE", 0)
    # No sample materialised for an unobserved label set.
    assert _val(em, "scraper_urls_collected_total", {"portal": "autoscout24", "country": "DE"}) is None


@pytest.mark.unit
def test_record_null_field_rate_sets_gauge(em: EngineMetrics) -> None:
    em.record_null_field_rate("leboncoin", 0.23)
    assert _val(em, "scraper_null_field_rate", {"portal": "leboncoin"}) == pytest.approx(0.23)


@pytest.mark.unit
def test_record_null_field_rate_overwrites(em: EngineMetrics) -> None:
    em.record_null_field_rate("leboncoin", 0.5)
    em.record_null_field_rate("leboncoin", 0.1)
    assert _val(em, "scraper_null_field_rate", {"portal": "leboncoin"}) == pytest.approx(0.1)


@pytest.mark.unit
def test_record_poison_counts(em: EngineMetrics) -> None:
    em.record_poison("wallapop", 3)
    assert _val(em, "scraper_poison_detected_total", {"portal": "wallapop"}) == 3.0


@pytest.mark.unit
def test_record_schema_change_increments(em: EngineMetrics) -> None:
    em.record_schema_change("gocar")
    em.record_schema_change("gocar")
    assert _val(em, "scraper_schema_change_total", {"portal": "gocar"}) == 2.0


@pytest.mark.unit
def test_record_success_sets_explicit_timestamp(em: EngineMetrics) -> None:
    em.record_success("autoscout24", when=1_700_000_000.0)
    assert _val(em, "scraper_last_success_timestamp", {"portal": "autoscout24"}) == 1_700_000_000.0


@pytest.mark.unit
def test_record_success_defaults_to_now(em: EngineMetrics) -> None:
    em.record_success("autoscout24")
    assert _val(em, "scraper_last_success_timestamp", {"portal": "autoscout24"}) > 0.0


# --------------------------------------------------------------------------- #
# per identity
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_record_trust_score(em: EngineMetrics) -> None:
    em.record_trust_score("id-1", "FR", 7.5)
    assert _val(em, "identity_trust_score", {"identity_id": "id-1", "country": "FR"}) == pytest.approx(7.5)


@pytest.mark.unit
def test_record_identity_ban_count(em: EngineMetrics) -> None:
    em.record_identity_ban_count("id-1", "FR", 4)
    assert _val(em, "identity_ban_count", {"identity_id": "id-1", "country": "FR"}) == 4.0


@pytest.mark.unit
def test_record_identity_status_one_hot(em: EngineMetrics) -> None:
    statuses = ("active", "quarantined", "retired")
    em.record_identity_status("id-1", "quarantined", statuses)
    assert _val(em, "identity_status", {"identity_id": "id-1", "status": "quarantined"}) == 1.0
    assert _val(em, "identity_status", {"identity_id": "id-1", "status": "active"}) == 0.0
    assert _val(em, "identity_status", {"identity_id": "id-1", "status": "retired"}) == 0.0


@pytest.mark.unit
def test_record_identity_status_transition_clears_previous(em: EngineMetrics) -> None:
    statuses = ("active", "quarantined")
    em.record_identity_status("id-1", "active", statuses)
    em.record_identity_status("id-1", "quarantined", statuses)
    assert _val(em, "identity_status", {"identity_id": "id-1", "status": "active"}) == 0.0
    assert _val(em, "identity_status", {"identity_id": "id-1", "status": "quarantined"}) == 1.0


# --------------------------------------------------------------------------- #
# per proxy
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_record_proxy_success_rate(em: EngineMetrics) -> None:
    em.record_proxy_success_rate("203.0.113.7", "isp_sticky", "DE", 0.92)
    labels = {"proxy_ip": "203.0.113.7", "tier": "isp_sticky", "country": "DE"}
    assert _val(em, "proxy_success_rate", labels) == pytest.approx(0.92)


@pytest.mark.unit
def test_record_proxy_ban_count(em: EngineMetrics) -> None:
    em.record_proxy_ban_count("203.0.113.7", "decodo", 2)
    assert _val(em, "proxy_ban_count_24h", {"proxy_ip": "203.0.113.7", "provider": "decodo"}) == 2.0


# --------------------------------------------------------------------------- #
# pipeline
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_record_delta_new_and_gone(em: EngineMetrics) -> None:
    em.record_delta("autoscout24", "DE", new=12, gone=3)
    assert _val(em, "pipeline_delta_new_total", {"source": "autoscout24", "country": "DE"}) == 12.0
    assert _val(em, "pipeline_delta_gone_total", {"source": "autoscout24", "country": "DE"}) == 3.0


@pytest.mark.unit
def test_record_delta_zero_is_noop(em: EngineMetrics) -> None:
    em.record_delta("autoscout24", "DE", new=0, gone=0)
    assert _val(em, "pipeline_delta_new_total", {"source": "autoscout24", "country": "DE"}) is None
    assert _val(em, "pipeline_delta_gone_total", {"source": "autoscout24", "country": "DE"}) is None


@pytest.mark.unit
def test_record_enrich_success_rate(em: EngineMetrics) -> None:
    em.record_enrich_success_rate("autoscout24", 0.81)
    assert _val(em, "pipeline_enrich_success_rate", {"source": "autoscout24"}) == pytest.approx(0.81)


@pytest.mark.unit
def test_record_price_change(em: EngineMetrics) -> None:
    em.record_price_change("autoscout24", "DE", 5)
    assert _val(em, "pipeline_price_change_total", {"source": "autoscout24", "country": "DE"}) == 5.0


@pytest.mark.unit
def test_set_dlq_size(em: EngineMetrics) -> None:
    em.set_dlq_size(137)
    assert _val(em, "pipeline_dlq_size") == 137.0


# --------------------------------------------------------------------------- #
# system gauges + circuit encoding
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_set_warming_pool_size(em: EngineMetrics) -> None:
    em.set_warming_pool_size(8)
    assert _val(em, "warming_pool_size") == 8.0


@pytest.mark.unit
def test_set_premium_identity_count(em: EngineMetrics) -> None:
    em.set_premium_identity_count(4)
    assert _val(em, "premium_identity_count") == 4.0


@pytest.mark.unit
@pytest.mark.parametrize("state,code", [("closed", 0.0), ("half_open", 1.0), ("open", 2.0)])
def test_set_circuit_state_encoding(em: EngineMetrics, state: str, code: float) -> None:
    em.set_circuit_state("autoscout24.de", "t1", state)
    assert _val(em, "circuit_breaker_state", {"domain": "autoscout24.de", "tier": "t1"}) == code


@pytest.mark.unit
def test_set_circuit_state_unknown_defaults_to_closed(em: EngineMetrics) -> None:
    em.set_circuit_state("autoscout24.de", "t1", "garbage")
    assert _val(em, "circuit_breaker_state", {"domain": "autoscout24.de", "tier": "t1"}) == 0.0


# --------------------------------------------------------------------------- #
# module wrappers — must never raise, in normal or degraded mode
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_module_wrappers_do_not_raise() -> None:
    metrics.record_request("autoscout24", "t1", 200, 0.1)
    metrics.record_urls_collected("autoscout24", "DE", 42)
    metrics.record_null_field_rate("autoscout24", 0.05)
    metrics.record_success("autoscout24")
    metrics.record_trust_score("id-x", "DE", 1.0)
    metrics.set_dlq_size(0)
    metrics.set_circuit_state("autoscout24.de", "t1", "closed")


@pytest.mark.unit
def test_wrappers_are_noop_in_degraded_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metrics, "_PROM", False)
    monkeypatch.setattr(metrics, "_METRICS", None)
    monkeypatch.setattr(metrics, "_degraded_warned", False)
    assert metrics.is_available() is False
    # None of these should raise even though prometheus is "unavailable".
    metrics.record_request("p", "t", 200, 0.1)
    metrics.record_urls_collected("p", "DE", 7)
    metrics.record_null_field_rate("p", 0.1)
    metrics.record_success("p")
    metrics.record_trust_score("i", "DE", 1.0)
    metrics.set_dlq_size(1)
    metrics.set_circuit_state("d", "t", "open")
    assert metrics.start() is False


@pytest.mark.unit
def test_engine_metrics_raises_in_degraded_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metrics, "_PROM", False)
    with pytest.raises(RuntimeError):
        EngineMetrics()


# --------------------------------------------------------------------------- #
# soft-block: NullFieldTracker
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_null_tracker_empty_is_not_blocked() -> None:
    t = NullFieldTracker()
    assert t.rate == 0.0
    assert t.is_soft_blocked is False
    assert t.sample_count == 0


@pytest.mark.unit
def test_null_tracker_partial_window_never_blocks() -> None:
    t = NullFieldTracker(window=10)
    for _ in range(9):
        t.record(missing_critical=True)  # 100% missing but window not full
    assert t.is_full is False
    assert t.is_soft_blocked is False


@pytest.mark.unit
def test_null_tracker_blocks_above_threshold_when_full() -> None:
    t = NullFieldTracker(window=10, threshold=0.15)
    for _ in range(2):
        t.record(missing_critical=True)
    for _ in range(8):
        t.record(missing_critical=False)
    assert t.is_full is True
    assert t.rate == pytest.approx(0.2)
    assert t.is_soft_blocked is True


@pytest.mark.unit
def test_null_tracker_at_threshold_does_not_block() -> None:
    # 1/10 = 0.10 which is below the 0.15 threshold → no block.
    t = NullFieldTracker(window=10, threshold=0.15)
    t.record(missing_critical=True)
    for _ in range(9):
        t.record(missing_critical=False)
    assert t.rate == pytest.approx(0.1)
    assert t.is_soft_blocked is False


@pytest.mark.unit
def test_null_tracker_window_slides() -> None:
    t = NullFieldTracker(window=10, threshold=0.15)
    for _ in range(10):
        t.record(missing_critical=True)  # window all-missing → blocked
    assert t.is_soft_blocked is True
    for _ in range(10):
        t.record(missing_critical=False)  # slide window to all-clean
    assert t.rate == 0.0
    assert t.is_soft_blocked is False


@pytest.mark.unit
def test_null_tracker_reset_clears_window() -> None:
    t = NullFieldTracker(window=10)
    for _ in range(10):
        t.record(missing_critical=True)
    t.reset()
    assert t.sample_count == 0
    assert t.is_soft_blocked is False


@pytest.mark.unit
def test_null_tracker_invalid_window_raises() -> None:
    with pytest.raises(ValueError):
        NullFieldTracker(window=0)


# --------------------------------------------------------------------------- #
# soft-block: ZeroUrlTracker
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_zero_url_tracker_below_threshold_not_blocked() -> None:
    t = ZeroUrlTracker(cycles=3)
    t.record(0)
    t.record(0)
    assert t.consecutive_empty == 2
    assert t.is_soft_blocked is False


@pytest.mark.unit
def test_zero_url_tracker_three_consecutive_blocks() -> None:
    t = ZeroUrlTracker(cycles=3)
    t.record(0)
    t.record(0)
    t.record(0)
    assert t.consecutive_empty == 3
    assert t.is_soft_blocked is True


@pytest.mark.unit
def test_zero_url_tracker_nonempty_resets_run() -> None:
    t = ZeroUrlTracker(cycles=3)
    t.record(0)
    t.record(0)
    t.record(20)  # a real cycle resets the empty run
    assert t.consecutive_empty == 0
    assert t.is_soft_blocked is False
    t.record(0)
    assert t.consecutive_empty == 1


@pytest.mark.unit
def test_zero_url_tracker_reset_clears() -> None:
    t = ZeroUrlTracker(cycles=3)
    t.record(0)
    t.record(0)
    t.record(0)
    t.reset()
    assert t.consecutive_empty == 0
    assert t.is_soft_blocked is False


@pytest.mark.unit
def test_zero_url_tracker_invalid_cycles_raises() -> None:
    with pytest.raises(ValueError):
        ZeroUrlTracker(cycles=0)


# --------------------------------------------------------------------------- #
# soft-block constants match the design contract
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_softblock_constants_match_spec() -> None:
    assert softblock.SOFT_BLOCK_RATE == 0.15
    assert softblock.SOFT_BLOCK_WINDOW == 10
    assert softblock.ZERO_URL_CYCLES == 3
