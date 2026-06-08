# CARDEX VPS — Sizing & Cost

Resource driver = **parallel Camoufox (Firefox) browsers** for T2/T3 giants. Measured
baseline (stealth front): **4 browsers → ~6.4 h to enumerate mobile.de entirely (1.58 M
listings)** ⇒ ≈ **61 K listings / browser / hour** (count+preview enumeration). Each
Camoufox instance costs **~0.5–0.7 GB RAM + ~0.5–1 vCPU** (render-bound).

## What runs and what it costs (steady state)
| Component | RAM | vCPU |
|---|---:|---:|
| Postgres (2M-entity target) | 4–8 GB | 2–4 |
| Redis (streams, noeviction) | 2–4 GB | 0.5–1 |
| Entity API + seam workers (delta/enrich/rich/dispatcher) | ~1.2 GB | ~1.5 |
| 6 country coordinators (1–2 Camoufox each) | 6–10 GB | 4–8 |
| Discovery (orchestrator + domain-resolver) | ~0.5 GB | ~0.5 |
| **Total working set** | **~14–24 GB** | **~8–16** |

## Throughput math (giants)
- 6 giants ≈ **~5 M** listings total. To enumerate all continuously in **~24 h**:
  5 M / 24 h ≈ **208 K/h** ⇒ ≈ **3.4 browsers** running non-stop. **4–8 browsers** gives
  headroom + per-country isolation. 8 browsers → full 6-giant sweep in **~12–15 h**.
- mobile.de alone, full: **~6.4 h @ 4 browsers** / **~3.2 h @ 8 browsers**.

## Postgres disk at the 2M target
- 2 M entities × pointer inventory (vehicle_index ≈ 200 B/row, partitioned events) →
  **~20–100 M rows** ⇒ **~30–60 GB** table+index; rich `vehicles` for a subset adds
  ~5–15 GB. WAL + backups + growth ⇒ **provision 240 GB NVMe min, 480 GB comfortable.**
- NVMe is required (`random_page_cost=1.1`, `effective_io_concurrency=200` assume SSD).
- `shared_buffers` ≈ 25 % RAM, `effective_cache_size` ≈ 75 % (set in `.env`).

## Recommended VPS tiers
| Tier | Spec | Camoufox || Provider example | €/mo* |
|---|---|---:|---|---|---:|
| **Validate-at-scale** | 8 vCPU / 16 GB / 240 GB NVMe | 4–6 || Hetzner **CPX41** | ~€30 |
| **Production (recommended)** | 16 vCPU / 32 GB / 360 GB NVMe | 8–12 || Hetzner **CPX51** | ~€63 |
| **Browser-heavy (dedicated CPU)** | 8 dedic vCPU / 32 GB / 240 GB | 8–10 || Hetzner **CCX33** | ~€97 |
| Budget (shared CPU) | 8 vCPU / 30 GB / 800 GB SSD | 4–6 || **Contabo VPS L** | ~€18–25 |
| Budget XL | 16 vCPU / 60 GB / 1.6 TB SSD | 8–12 || **Contabo VPS XL** | ~€35–45 |
| Balanced | 8 vCPU / 24 GB / 200 GB | 4–6 || **OVH** Comfort | ~€35–50 |

\* Approximate 2026 list prices, EUR, ex-VAT. Hetzner = best price/perf on real vCPU;
Contabo = cheapest but **shared** CPU (Camoufox is CPU-bound → prefer Hetzner CCX/CPX or
OVH for sustained browser throughput); OVH = middle.

**Recommendation:** start on **Hetzner CPX51 (~€63/mo)** — 8–12 parallel Camoufox, PG 8 GB,
Redis 4 GB, full 6-giant sweep in ~12–15 h with room for discovery toward 2M. Drop to
CPX41 for pure validation; move to a dedicated-CPU CCX line only if render becomes the bottleneck.

## The real cost driver is NOT the VPS — it's the residential proxies
T3 (DataDome: lacentrale, milanuncios, promoneuve) needs **residential rotating** IPs
(Oxylabs / Decodo / Bright Data): **~€8–15 / GB** or **~€300+/mo** for a pool. Budget this
separately; the VPS is the cheap part. Fill `RESIDENTIAL_PROXY_<CC>` only for the countries
you're actively cracking to control spend.

## Tuning knobs (`.env`)
`SCRAPER_MEM` (per-coordinator cap), `CYCLE_WAIT_SECONDS` (re-harvest cadence),
`ENRICH_CONCURRENCY`, `PG_SHARED_BUFFERS`, `PG_EFFECTIVE_CACHE`, `REDIS_MAXMEMORY`.
Scale Camoufox by adding/raising per-country coordinators (and RAM accordingly).
