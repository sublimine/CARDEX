# CARDEX — Innoweb-Style Litigation Mitigation

> **Scope:** Technical and operational controls that distinguish CARDEX batch-indexing from
> the real-time proxy held infringing in *C-202/12 Innoweb v Wegener*.
> All controls must remain in place; any change requires a legal sign-off.

---

## 1. Legal Backdrop

### C-202/12 Innoweb v Wegener (CJEU, 19 Dec 2013)

| Element | Innoweb (infringing) | CARDEX (safe) |
|---|---|---|
| Query routing | Real-time forwarding to source sites | Batch crawl; no live query relay |
| Caching | Transparent pass-through proxy | Structured ETL into own SQLite/Postgres |
| Source visibility | User sees source HTML inline | User sees CARDEX-normalised record |
| Transformation | None — raw source response served | Full field normalisation + quality pipeline |
| Temporal coupling | Sub-second; user sees live source data | 24-hour minimum refresh cycle |

**Legal principle (para. 49-51):** A meta-search service that provides a dedicated, systematic means of querying and displaying source content in real time substitutes for the source and infringes the sui generis database right. A batch index that transforms and re-presents the data does not.

---

## 2. Implemented Controls

### 2.1 No Real-Time Query Relay

```
Prohibited pattern:  User query → CARDEX → live relay to mobile.de → result
CARDEX actual:       User query → CARDEX local index → result
```

- All crawls are scheduled batch jobs (cron `REFRESH_STRATEGY.md §3`).
- No HTTP request to a source site is ever triggered in response to a user query.
- Enforcement: the `gateway` service has no outbound HTTP client on the request path; only the `extractor` worker (async) does.

### 2.2 Volume Cap per Source

Each extractor worker enforces a per-source hourly cap defined in `extractor/config/sources.toml`:

```toml
[source.mobile_de]
max_records_per_run   = 5_000
min_interval_seconds  = 86_400   # 24 hours
request_delay_ms      = 1_500    # ≥ 1.5 s between requests
```

Rationale: disproportionate volume extraction could trigger a "substantial part" claim even in a batch model. Caps ensure CARDEX never systematically re-extracts the entire database of any single source within a 24-hour window.

### 2.3 Minimum Request Latency (≥ 1 500 ms)

All extractor HTTP clients enforce `time.Sleep(requestDelay)` between consecutive requests to the same host. This:

- Signals non-automated intent to source robots.txt parsers.
- Prevents cache-busting / flooding that would undermine the "batch" characterisation.
- Complies with `robots.txt` `Crawl-delay` directives where specified.

### 2.4 Data Transformation — Structured ETL

CARDEX does not cache or re-serve raw source HTML. Every extracted record passes through:

```
raw HTML → E-series extractor → normalised Vehicle struct → quality pipeline → own DB schema
```

Fields are mapped to CARDEX's internal schema (make, model, price_eur, mileage_km, etc.). The original source presentation is discarded. This satisfies the *transformation* criterion that distinguishes a database from a proxy.

### 2.5 Per-Source Attribution and `noindex` Respect

- Original `source_url` is stored internally for provenance but **not displayed** to end users in search results.
- CARDEX respects `X-Robots-Tag: noindex` and `<meta name="robots" content="noindex">` directives encountered during crawl.
- Source attribution in the UI is limited to the source name (e.g. "mobile.de") not a live link to the listing.

### 2.6 Volume Logging and Audit Trail

The `extractor` emits structured logs per run:

```json
{
  "source": "mobile.de",
  "run_id": "uuid",
  "started_at": "2026-04-16T03:00:00Z",
  "records_fetched": 1842,
  "records_rejected_quality": 124,
  "duration_s": 312
}
```

Logs are retained for **90 days** (see `08_OBSERVABILITY.md`). If a source operator challenges a specific crawl, CARDEX can demonstrate:
1. The run fell within per-source caps.
2. No real-time relay occurred.
3. Minimum inter-request delay was respected.

---

## 3. Distinction Table: CARDEX vs. Infringing Proxy

| Criterion (Innoweb test) | CARDEX implementation | Legal characterisation |
|---|---|---|
| Real-time query relay | **NO** — batch-only | Safe |
| Serves raw source content | **NO** — ETL normalisation | Safe |
| Substitutes for source | **NO** — own structured DB | Safe |
| Substantial part / systematic re-extraction | Capped at 5 000 records/source/day | Safe (proportionate sampling) |
| `robots.txt` compliance | **YES** | Safe |
| Attribution to source | Source name only, no live iframe | Safe |
| Iframe / live preview | **PROHIBITED** (VG Bild-Kunst C-392/19) | Permanent product constraint |

---

## 4. Residual Risks and Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Source operator claims "substantial part" despite cap | Low | Volume logs + 24 h minimum cycle evidence |
| sui generis DB right claim (non-EU source operators after CH/UK divergence) | Medium | Swiss MSchG Art. 2 (adapted) + contract clauses in dealer onboarding ToS |
| Real-time preview feature added by future dev without legal review | Medium | **Architecture gate:** PR template checklist item — "Does this add outbound HTTP on the request path?" |
| Framing via future "listing preview" feature | Low | Product-level ban documented; reviewed in security hardening (`09_SECURITY_HARDENING.md §7`) |

---

## 5. Mandatory Change-Gate Checklist

Any PR that touches `extractor/`, `gateway/`, or the frontend "vehicle detail" view must confirm:

- [ ] No outbound HTTP on the synchronous request path
- [ ] Per-source cap unchanged or reduced (never increased without legal sign-off)
- [ ] No iframe or `<embed>` of third-party URLs introduced
- [ ] Request delay not reduced below 1 500 ms
- [ ] Volume logging still emitted

---

*Last reviewed: 2026-04-16. Next review: before any extractor architecture change or source contract renewal.*
