"""
Prometheus metrics — todas las métricas del scraping engine.

Expuestas en :9090/metrics. Consumidas por Grafana + las 5 alertas de
SCRAPING_ENGINE.md §E (ver alerts.yml).

Diseño:
  * `EngineMetrics` encapsula un CollectorRegistry propio con TODAS las series.
    Es directamente testeable: se instancia con un registry aislado y se leen
    los valores con `registry.get_sample_value(...)` sin tocar estado global.
  * El módulo expone un singleton perezoso + wrappers finos para el coordinator.
  * Degradación elegante: si `prometheus_client` no está instalado, el módulo
    no revienta — todas las funciones son no-ops y `is_available()` es False.
    Mismo patrón que tcp.py / sensor.py: el engine corre, solo pierde telemetría.

Métricas críticas de operación (no vanity):
  scraper_null_field_rate > 15% → soft block en curso → alert inmediato
  premium_identity_count < 3    → riesgo de no poder cubrir T3
  pipeline_dlq_size creciente   → upstream failures acumulándose
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

try:  # prometheus_client es opcional en tiempo de import (robustez/test).
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        start_http_server,
    )

    _PROM = True
except ImportError:  # pragma: no cover - exercised only without the dependency
    _PROM = False

# Circuit-breaker state encoding for the circuit_breaker_state gauge.
_CIRCUIT_CODE = {"closed": 0.0, "half_open": 1.0, "open": 2.0}

# Latency buckets tuned for scraping (sub-second to slow Camoufox sessions).
_DURATION_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)


def is_available() -> bool:
    """True when prometheus_client is importable and metrics are real."""
    return _PROM


class EngineMetrics:
    """All scraping-engine Prometheus series, scoped to one registry."""

    def __init__(self, registry: "CollectorRegistry | None" = None) -> None:
        if not _PROM:
            raise RuntimeError("prometheus_client not installed; use module wrappers")
        self.registry = registry or CollectorRegistry()
        reg = self.registry

        # ── Por portal + tier ────────────────────────────────────────────────
        self.requests = Counter(
            "scraper_requests", "HTTP requests issued",
            ["portal", "tier", "status_code"], registry=reg,
        )
        self.request_duration = Histogram(
            "scraper_request_duration_seconds", "Request latency",
            ["portal", "tier"], buckets=_DURATION_BUCKETS, registry=reg,
        )
        self.urls_collected = Counter(
            "scraper_urls_collected", "Listing URLs collected",
            ["portal", "country"], registry=reg,
        )
        self.null_field_rate = Gauge(
            "scraper_null_field_rate", "Fraction of records missing critical fields",
            ["portal"], registry=reg,
        )
        self.poison_detected = Counter(
            "scraper_poison_detected", "Poisoned responses discarded",
            ["portal"], registry=reg,
        )
        self.schema_change = Counter(
            "scraper_schema_change", "Schema fingerprint changes observed",
            ["portal"], registry=reg,
        )
        self.last_success_ts = Gauge(
            "scraper_last_success_timestamp", "Unix time of last successful scrape",
            ["portal"], registry=reg,
        )

        # ── Por identidad ────────────────────────────────────────────────────
        self.trust_score = Gauge(
            "identity_trust_score", "Per-identity trust score",
            ["identity_id", "country"], registry=reg,
        )
        self.identity_ban_count = Gauge(
            "identity_ban_count", "Per-identity cumulative ban count",
            ["identity_id", "country"], registry=reg,
        )
        self.identity_status = Gauge(
            "identity_status", "Per-identity status (1 = current)",
            ["identity_id", "status"], registry=reg,
        )

        # ── Por proxy ────────────────────────────────────────────────────────
        self.proxy_success_rate = Gauge(
            "proxy_success_rate", "Rolling proxy success rate",
            ["proxy_ip", "tier", "country"], registry=reg,
        )
        self.proxy_ban_count_24h = Gauge(
            "proxy_ban_count_24h", "Proxy bans in the last 24h",
            ["proxy_ip", "provider"], registry=reg,
        )

        # ── Pipeline ─────────────────────────────────────────────────────────
        self.delta_new = Counter(
            "pipeline_delta_new", "New listings detected",
            ["source", "country"], registry=reg,
        )
        self.delta_gone = Counter(
            "pipeline_delta_gone", "Listings gone",
            ["source", "country"], registry=reg,
        )
        self.enrich_success_rate = Gauge(
            "pipeline_enrich_success_rate", "Enrichment success rate",
            ["source"], registry=reg,
        )
        self.dlq_size = Gauge(
            "pipeline_dlq_size", "Dead-letter queue depth", registry=reg,
        )
        self.price_change = Counter(
            "pipeline_price_change", "Price changes detected",
            ["source", "country"], registry=reg,
        )

        # ── Sistema ──────────────────────────────────────────────────────────
        self.warming_pool_size = Gauge(
            "warming_pool_size", "Active, warmed identities ready to extract", registry=reg,
        )
        self.premium_identity_count = Gauge(
            "premium_identity_count", "Identities with trust_score >= 7.0", registry=reg,
        )
        self.circuit_breaker_state = Gauge(
            "circuit_breaker_state", "Circuit state (0 closed, 1 half_open, 2 open)",
            ["domain", "tier"], registry=reg,
        )

    # ── recording API ────────────────────────────────────────────────────────

    def record_request(self, portal: str, tier: str, status_code: int, duration_s: float) -> None:
        self.requests.labels(portal=portal, tier=tier, status_code=str(status_code)).inc()
        self.request_duration.labels(portal=portal, tier=tier).observe(duration_s)

    def record_urls_collected(self, portal: str, country: str, count: int) -> None:
        if count:
            self.urls_collected.labels(portal=portal, country=country).inc(count)

    def record_null_field_rate(self, portal: str, rate: float) -> None:
        self.null_field_rate.labels(portal=portal).set(rate)

    def record_poison(self, portal: str, count: int = 1) -> None:
        self.poison_detected.labels(portal=portal).inc(count)

    def record_schema_change(self, portal: str) -> None:
        self.schema_change.labels(portal=portal).inc()

    def record_success(self, portal: str, when: float | None = None) -> None:
        self.last_success_ts.labels(portal=portal).set(when if when is not None else time.time())

    def record_trust_score(self, identity_id: str, country: str, score: float) -> None:
        self.trust_score.labels(identity_id=identity_id, country=country).set(score)

    def record_identity_ban_count(self, identity_id: str, country: str, count: int) -> None:
        self.identity_ban_count.labels(identity_id=identity_id, country=country).set(count)

    def record_identity_status(self, identity_id: str, status: str, active_statuses: tuple[str, ...]) -> None:
        """Set the active status to 1 and every other known status to 0 for this id."""
        for st in active_statuses:
            self.identity_status.labels(identity_id=identity_id, status=st).set(1.0 if st == status else 0.0)

    def record_proxy_success_rate(self, proxy_ip: str, tier: str, country: str, rate: float) -> None:
        self.proxy_success_rate.labels(proxy_ip=proxy_ip, tier=tier, country=country).set(rate)

    def record_proxy_ban_count(self, proxy_ip: str, provider: str, count: int) -> None:
        self.proxy_ban_count_24h.labels(proxy_ip=proxy_ip, provider=provider).set(count)

    def record_delta(self, source: str, country: str, new: int = 0, gone: int = 0) -> None:
        if new:
            self.delta_new.labels(source=source, country=country).inc(new)
        if gone:
            self.delta_gone.labels(source=source, country=country).inc(gone)

    def record_enrich_success_rate(self, source: str, rate: float) -> None:
        self.enrich_success_rate.labels(source=source).set(rate)

    def record_price_change(self, source: str, country: str, count: int = 1) -> None:
        self.price_change.labels(source=source, country=country).inc(count)

    def set_dlq_size(self, size: int) -> None:
        self.dlq_size.set(size)

    def set_warming_pool_size(self, size: int) -> None:
        self.warming_pool_size.set(size)

    def set_premium_identity_count(self, count: int) -> None:
        self.premium_identity_count.set(count)

    def set_circuit_state(self, domain: str, tier: str, state: str) -> None:
        self.circuit_breaker_state.labels(domain=domain, tier=tier).set(_CIRCUIT_CODE.get(state, 0.0))


# ── module singleton + thin wrappers (coordinator-facing) ─────────────────────

_METRICS: EngineMetrics | None = None
_degraded_warned = False


def _get() -> EngineMetrics | None:
    """Lazily build the default-registry metrics, or None when degraded."""
    global _METRICS, _degraded_warned
    if not _PROM:
        if not _degraded_warned:
            log.warning("prometheus_client not installed — metrics disabled (degraded mode)")
            _degraded_warned = True
        return None
    if _METRICS is None:
        _METRICS = EngineMetrics()
    return _METRICS


def start(port: int = 9090) -> bool:
    """Start the Prometheus HTTP exporter. Returns False in degraded mode."""
    if not _PROM:
        _get()  # emit the degraded warning once
        return False
    start_http_server(port, registry=_get().registry)  # type: ignore[union-attr]
    log.info("prometheus exporter listening on :%d/metrics", port)
    return True


def record_request(portal: str, tier: str, status_code: int, duration_s: float) -> None:
    m = _get()
    if m:
        m.record_request(portal, tier, status_code, duration_s)


def record_urls_collected(portal: str, country: str, count: int) -> None:
    m = _get()
    if m:
        m.record_urls_collected(portal, country, count)


def record_null_field_rate(portal: str, rate: float) -> None:
    m = _get()
    if m:
        m.record_null_field_rate(portal, rate)


def record_success(portal: str, when: float | None = None) -> None:
    m = _get()
    if m:
        m.record_success(portal, when)


def record_trust_score(identity_id: str, country: str, score: float) -> None:
    m = _get()
    if m:
        m.record_trust_score(identity_id, country, score)


def set_dlq_size(size: int) -> None:
    m = _get()
    if m:
        m.set_dlq_size(size)


def set_circuit_state(domain: str, tier: str, state: str) -> None:
    m = _get()
    if m:
        m.set_circuit_state(domain, tier, state)
