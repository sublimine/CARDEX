"""
Prometheus metrics — todas las métricas del scraping engine.

Expuestas en :9090/metrics. Consumidas por Grafana dashboard.
5 alertas activas definidas en SCRAPING_ENGINE.md §E.

Métricas críticas de operación (no vanity):
  scraper_null_field_rate > 15% → soft block en curso → alert inmediato
  premium_identity_count < 3    → riesgo de no poder cubrir T3
  pipeline_dlq_size creciente   → upstream failures acumulándose
"""
from __future__ import annotations

# Implementation requires: prometheus_client package
# from prometheus_client import Counter, Histogram, Gauge, start_http_server

# --- Por portal + tier ---
# scraper_requests_total{portal, tier, status_code}
# scraper_request_duration_seconds{portal, tier}      # histogram
# scraper_urls_collected_total{portal, country}
# scraper_null_field_rate{portal}                     # CRÍTICO: > 15% = soft block
# scraper_poison_detected_total{portal}
# scraper_schema_change_total{portal}
# scraper_last_success_timestamp{portal}              # para alerta ScraperStale

# --- Por identidad ---
# identity_trust_score{identity_id, country}
# identity_ban_count{identity_id, country}
# identity_status{identity_id, status}

# --- Por proxy ---
# proxy_success_rate{proxy_ip, tier, country}
# proxy_ban_count_24h{proxy_ip, provider}

# --- Pipeline ---
# pipeline_delta_new_total{source, country}
# pipeline_delta_gone_total{source, country}
# pipeline_enrich_success_rate{source}
# pipeline_dlq_size
# pipeline_price_change_total{source, country}

# --- Sistema ---
# warming_pool_size           — identidades status=active, warming_done=true
# premium_identity_count      — trust_score >= 7.0
# circuit_breaker_state{domain, tier}


def start(port: int = 9090) -> None:
    """Start Prometheus HTTP server."""
    raise NotImplementedError


def record_request(portal: str, tier: str, status_code: int, duration_s: float) -> None:
    raise NotImplementedError


def record_null_field_rate(portal: str, rate: float) -> None:
    raise NotImplementedError


def record_trust_score(identity_id: str, country: str, score: float) -> None:
    raise NotImplementedError
