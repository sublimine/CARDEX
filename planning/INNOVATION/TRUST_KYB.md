# CARDEX Trust KYB — Dealer Portable Trust Profile

**Sprint:** 34 | **Branch:** `sprint/34-trust-kyb`
**Status:** Complete | **Port:** `:8505`

## Overview

The Trust KYB (Know Your Business) engine computes a portable, verifiable trust
credential for every dealer in the CARDEX index. Dealers build trust over time;
counterparties (buyers, auction platforms, other dealers) can verify credentials
via the public badge URL without sharing raw data.

## Trust Score Composition (100 pts max)

| Signal | Weight | Max Pts | How Derived |
|--------|--------|---------|-------------|
| VIES VAT Verification | 20% | 20 | `valid`=20, `unchecked`=10, `invalid`=0 |
| Commercial Registry | 15% | 15 | `registered`+age bonus, `unchecked`=7, `not_found`=0 |
| V15 Trust Score (quality pipeline) | 20% | 20 | V15 0–100 mapped linearly; **capped at 10 pts for first 30 days** (trust ramp-up) |
| Behavioral signals | 25% | 25 | Volume (8) + composite score (10) + index tenure (7) |
| Anomaly absence | 20% | 20 | 20 − (4 × anomaly_count), floor 0 |

### Trust Tiers

| Tier | Score | Badge Colour |
|------|-------|--------------|
| Platinum | ≥ 85 | Gold `#FFD700` |
| Gold | ≥ 70 | Silver `#C0C0C0` |
| Silver | ≥ 50 | Bronze `#CD7F32` |
| Unverified | < 50 | Grey `#9E9E9E` |

### Trust Ramp-Up Rule

New dealers (index tenure < 30 days) have their V15 contribution **capped at 50%
of maximum** (10 pts instead of up to 20). This prevents freshly-created accounts
from achieving high tiers before establishing behavioral history. The cap lifts
automatically after day 30.

### Behavioral Sub-Scores

- **Volume (0–8 pts):** `min(8, listings / 50 × 8)` — 50 active listings = full
- **Composite quality (0–10 pts):** `avg_composite / 100 × 10`
- **Index tenure (0–7 pts):** `min(7, tenure_days / 365 × 7)` — 1 year = full

## Profile Credential

Each `DealerTrustProfile` is:
- **Valid for 90 days** (rolling window, auto-refreshed weekly by the daemon)
- **Tamper-evident** via `profile_hash` = SHA-256(`dealer_id:score:issued_at_unix`)
- **Verifiable** at `GET /trust/verify/{hash}` without disclosing raw data

## eIDAS 2 Readiness

The `eidas_wallet_did` field is present (empty) on every profile.

When EU eIDAS 2 Regulation (EU) 910/2014 amendments enter force (expected
2026–2027), this field will hold the W3C DID of the dealer's EU Digital Identity
Wallet, enabling:

1. Wallet-to-wallet credential exchange (no central CARDEX intermediary)
2. Zero-knowledge proof of tier tier without score disclosure
3. Cross-border automatic recognition under EU law

**What changes when eIDAS 2 is live:**
- DID resolver integration (DID Web or DID Key)
- Verifiable Credential issuance via W3C VC Data Model 2.0
- Badge verification flow: relying party calls DID endpoint directly, CARDEX
  becomes optional trust anchor rather than single source of truth

## HTTP API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `GET` | `/trust/profile/{dealer_id}` | Full trust profile JSON |
| `GET` | `/trust/badge/{dealer_id}.svg` | Embeddable SVG badge (cache-able, 1h) |
| `GET` | `/trust/verify/{profile_hash}` | Verify badge authenticity |
| `POST` | `/trust/refresh/{dealer_id}` | Force-recompute profile |
| `GET` | `/trust/list?tier=&country=&limit=` | List profiles by tier/country |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TRUST_DB_PATH` | `./data/discovery.db` | Shared SQLite KG path |
| `TRUST_PORT` | `8505` | HTTP listen port |
| `TRUST_BADGE_BASE` | `http://localhost:8505` | Base URL for badge links |
| `TRUST_MIN_LISTINGS` | `5` | Min listings for eligibility |
| `CARDEX_TRUST_URL` | `http://localhost:8505` | CLI base URL |

## CLI Commands

```bash
# Full trust profile (ANSI table)
cardex trust show D_AUTOHAUS_001

# List platinum dealers in Germany
cardex trust list --tier platinum --country DE

# Force-recompute (e.g. after VIES verification update)
cardex trust refresh D_AUTOHAUS_001
```

## Badge Embedding (for Dealer Websites)

```html
<img src="https://trust.cardex.eu/trust/badge/DEALER_ID.svg"
     alt="CARDEX Trust Badge"
     width="180" height="36">
```

Verification link:
```html
<a href="https://trust.cardex.eu/trust/verify/PROFILE_HASH">
  Verify CARDEX Trust Badge
</a>
```

## SQLite Schema

```sql
CREATE TABLE dealer_trust_profiles (
  dealer_id           TEXT PRIMARY KEY,
  dealer_name         TEXT,
  country             TEXT,
  vat_id              TEXT,
  vies_status         TEXT,  -- valid | invalid | unchecked
  registry_status     TEXT,  -- registered | not_found | unchecked
  registry_age_years  INTEGER,
  v15_score           REAL,
  listing_volume      INTEGER,
  avg_composite_score REAL,
  index_tenure_days   INTEGER,
  anomaly_count       INTEGER,
  trust_score         REAL,
  trust_tier          TEXT,
  badge_url           TEXT,
  issued_at           TEXT,  -- RFC3339
  expires_at          TEXT,  -- RFC3339
  profile_hash        TEXT,
  eidas_wallet_did    TEXT   -- placeholder; empty until eIDAS 2
);
```

## Architecture

```
innovation/trust_kyb/
├── cmd/trust-service/main.go   HTTP server + weekly batch refresh daemon
├── internal/
│   ├── model/model.go           DealerTrustProfile struct + ComputeHash + IsExpired
│   ├── profiler/profiler.go     Weighted scoring engine (5 components)
│   ├── badge/badge.go           SVG badge generator (4 tier styles)
│   └── storage/storage.go      SQLite persistence + KG signal queries
```

## Test Coverage

| Package | Tests | Description |
|---------|-------|-------------|
| `internal/profiler` | 9 | Weight max 100, zero case, ramp-up cap, tier boundaries, hash determinism, expiration, breakdown sum, badge URL, eIDAS placeholder |
| `internal/badge` | 6 | All tiers render, labels present, unknown tier fallback, determinism, content type, platinum colour |

## Deployment

```bash
# Build
cd innovation/trust_kyb && GOWORK=off go build -o ../../bin/trust-service ./cmd/trust-service/
# or: make trust-build

# Run
TRUST_DB_PATH=/srv/cardex/db/discovery.db ./bin/trust-service
# or: make trust-serve

# Test
cd innovation/trust_kyb && GOWORK=off go test -race ./...
# or: make trust-test
```

RAM budget: ~30 MB idle (pure Go stdlib HTTP server + SQLite WAL reader).
CPU: negligible (arithmetic only, no ML inference).
