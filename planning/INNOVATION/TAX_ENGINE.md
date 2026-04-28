# TAX ENGINE — VAT Cross-Border Optimiser

**Sprint:** 32  |  **Branch:** `sprint/32-tax-engine`  |  **Port:** 8504  
**Package:** `innovation/tax_engine/` (Go module `cardex.eu/tax`)

---

## Purpose

Compute the optimal VAT route for B2B used-vehicle transactions across 6 countries:
**DE / FR / ES / BE / NL** (EU) and **CH** (non-EU). Covers all 30 directional pairs.

---

## Architecture

```
CLI: cardex tax --from ES --to DE --price 15000 --margin 2000 --seller-vat ...
            │
            │ POST /tax/calculate
            ▼
  ┌───────────────────────────────────────┐
  │  tax-server  :8504                    │
  │  ─────────────────────────────────── │
  │  VIESClient  (24h cache, concurrent) │
  │  Calculator  (rules.go + calc.go)    │
  └───────────────────────────────────────┘
```

**Request:**
```json
{
  "from_country": "ES",
  "to_country": "DE",
  "vehicle_price_cents": 1500000,
  "margin_cents": 200000,
  "seller_vat_id": "ESB12345678",
  "buyer_vat_id": "DE123456789",
  "vehicle_age_months": 0,
  "vehicle_km": 0
}
```

**Response:** Array of routes sorted cheapest-first (by VATAmount on equal TotalCost), with `optimal_route` alias.

---

## VAT Regimes

### 1. Margin Scheme (Art. 313-332 Directive 2006/112/CE)

Applicable when the seller originally acquired the vehicle without the right to
deduct input VAT (typically purchased from a private individual or under a prior
margin scheme). VAT is calculated **only on the dealer's gross margin**.

```
VAT = margin × rate / (1 + rate)    [VAT embedded in selling price]
```

The buyer receives **no deductible VAT invoice line** — the VAT is irrecoverable.

| Country | Rate  |
|---------|-------|
| DE      | 19%   |
| FR      | 20%   |
| ES      | 21%   |
| BE      | 21%   |
| NL      | 21%   |

**Legal basis:** Art. 313-332 Dir. 2006/112/CE; § 25a UStG (DE); Art. 297A-297F CGI (FR);
Art. 135-139 LIVA (ES); Art. 58 CTVA (BE); Art. 28b-g Wet OB (NL)

---

### 2. Intra-Community Acquisition (Art. 20/138 Dir. 2006/112/CE)

B2B zero-rated intra-EU supply. **Conditions:**
- Both seller and buyer have valid, VIES-verified VAT IDs.
- Seller issues invoice without VAT, including buyer's VAT ID.
- Buyer self-accounts (reverse-charge) in destination country.
- For a fully-taxable dealer: reverse-charge VAT is immediately deductible → **net VAT cost = 0**.
- Seller submits recapitulative statement (ES: Mod. 349 / DE: ZM / FR: DES).

**Effective rate:** 0% (zero-rated at source; reverse-charged and fully recovered in destination).

**Legal basis:** Art. 20, 138, 262 Dir. 2006/112/CE; § 6a UStG (DE); Art. 39 bis CGI (FR);
Art. 25 LIVA (ES); Art. 39-bis VAT Code (BE); Art. 9 Wet OB (NL)

---

### 3. Export/Import — CH↔EU

CH is not an EU member state. No intra-community regime applies across the CH border.

**EU → CH:**
- Export from EU at 0% VAT (customs export declaration EX-A / DAE required)
- Import to CH: MWST/TVA **8.1%** on CIF value at Swiss customs
- Swiss VAT-registered buyer: MWST input tax deductible

**CH → EU:**
- Export from CH at 0% MWST (Art. 23 MWSTG)
- Import to EU: destination country's standard VAT rate on declared customs value
- EU VAT-registered buyer: import VAT fully deductible as input tax

**Legal basis (EU→CH):** Art. 146(1)(a) Dir. 2006/112/CE; Art. 50-57 LTVA-CH; Reg. UE 952/2013 CAU  
**Legal basis (CH→EU):** Art. 23 MWSTG/LTVA-CH; Art. 200-203 Dir. 2006/112/CE; Reg. UE 952/2013 CAU

---

### 4. New Means of Transport (Art. 2(2)(b) Dir. 2006/112/CE)

A vehicle is **"new"** if EITHER:
- Supplied ≤ **6 months** after first entry into service, OR
- Has travelled ≤ **6 000 km**

For new vehicles on intra-EU routes:
- **Margin scheme is excluded** (Art. 311(1)(1) — only second-hand goods qualify)
- Intra-community supply is ALWAYS taxed in the **destination country** at the destination rate
- This applies even to private buyers (exceptional rule in EU VAT law)

---

## Full 30-Pair Matrix

### EU → EU (20 directional pairs)

| From | To | Margin Scheme Rate | Intra-Community (B2B, valid VIES) |
|------|----|--------------------|-----------------------------------|
| DE   | FR | 19%                | 0% (reverse-charge FR 20%)        |
| DE   | ES | 19%                | 0% (reverse-charge ES 21%)        |
| DE   | BE | 19%                | 0% (reverse-charge BE 21%)        |
| DE   | NL | 19%                | 0% (reverse-charge NL 21%)        |
| FR   | DE | 20%                | 0% (reverse-charge DE 19%)        |
| FR   | ES | 20%                | 0% (reverse-charge ES 21%)        |
| FR   | BE | 20%                | 0% (reverse-charge BE 21%)        |
| FR   | NL | 20%                | 0% (reverse-charge NL 21%)        |
| ES   | DE | 21%                | 0% (reverse-charge DE 19%)        |
| ES   | FR | 21%                | 0% (reverse-charge FR 20%)        |
| ES   | BE | 21%                | 0% (reverse-charge BE 21%)        |
| ES   | NL | 21%                | 0% (reverse-charge NL 21%)        |
| BE   | DE | 21%                | 0% (reverse-charge DE 19%)        |
| BE   | FR | 21%                | 0% (reverse-charge FR 20%)        |
| BE   | ES | 21%                | 0% (reverse-charge ES 21%)        |
| BE   | NL | 21%                | 0% (reverse-charge NL 21%)        |
| NL   | DE | 21%                | 0% (reverse-charge DE 19%)        |
| NL   | FR | 21%                | 0% (reverse-charge FR 20%)        |
| NL   | ES | 21%                | 0% (reverse-charge ES 21%)        |
| NL   | BE | 21%                | 0% (reverse-charge BE 21%)        |

**Optimal route for B2B with valid VIES: always Intra-Community (0% net VAT cost)**

### CH → EU (5 directional pairs)

| From | To | Regime         | Import VAT | Notes                                    |
|------|----|----------------|------------|------------------------------------------|
| CH   | DE | Export/Import  | 19%        | DUA customs; recoverable for DE dealers  |
| CH   | FR | Export/Import  | 20%        | DUA customs; recoverable for FR dealers  |
| CH   | ES | Export/Import  | 21%        | DUA customs; recoverable for ES dealers  |
| CH   | BE | Export/Import  | 21%        | DUA customs; recoverable for BE dealers  |
| CH   | NL | Export/Import  | 21%        | DUA customs; recoverable for NL dealers  |

### EU → CH (5 directional pairs)

| From | To | Regime         | CH Import VAT | Notes                                          |
|------|----|----------------|---------------|------------------------------------------------|
| DE   | CH | Export/Import  | 8.1% MWST     | EX-A export; Automobilsteuer +4% if < 3 years |
| FR   | CH | Export/Import  | 8.1% MWST     | EX-A export; recoverable for MWST-registered  |
| ES   | CH | Export/Import  | 8.1% MWST     | EX-A export; recoverable for MWST-registered  |
| BE   | CH | Export/Import  | 8.1% MWST     | EX-A export; recoverable for MWST-registered  |
| NL   | CH | Export/Import  | 8.1% MWST     | EX-A export; recoverable for MWST-registered  |

---

## VIES Integration

- REST API: `GET https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{cc}/vat/{number}`
- User-Agent: `CardexBot/1.0 tax-engine`
- Cache TTL: 24 hours (per VIES recommendation to avoid flooding)
- Concurrent validation for seller + buyer (goroutines)
- If VIES unavailable or returns error: defaults to `false` → margin scheme fallback

**VIES fallback rule:** If either VAT ID fails VIES validation (invalid or unavailable),
the intra-community regime is not offered. Only margin scheme is returned for EU-EU pairs.

---

## RAM / CPU Budget (Hetzner CX42)

| Component       | RAM   | CPU             |
|-----------------|-------|-----------------|
| tax-server idle | ~8 MB | negligible      |
| VIES call       | —     | ~10ms (network) |
| Calculation     | —     | < 1ms           |

The tax engine is the lightest of all innovation services. It is pure computation + network.

---

## Deployment

```bash
# Build and run
cd innovation/tax_engine
go build -o ../../bin/tax-server ./cmd/tax-server/
../../bin/tax-server

# Or via go run
go run ./cmd/tax-server/

# Environment variables
TAX_PORT=8504         # listen port (default: 8504)
CARDEX_TAX_URL=...    # used by CLI (default: http://localhost:8504)
```

---

## Edge Cases and Known Limitations

1. **CH Automobilsteuer:** Switzerland levies an additional 4% Automobilsteuer on passenger car imports
   if the vehicle is less than 3 years old. Not modelled (requires additional input field).

2. **VAT ID format validation:** The engine normalises IDs (uppercase, no spaces) but does not
   validate format per country. VIES API performs the definitive check.

3. **Margin scheme eligibility:** The engine assumes the seller is eligible for the margin scheme
   (i.e., bought the vehicle without deducting VAT). It does not verify purchase invoices.

4. **Intra-community: reverse-charge in destination:** The buyer's VAT liability in the destination
   country (reverse-charge) is correctly shown as net-zero for fully-taxable dealers. Partial
   exemption scenarios (mixed-use businesses) are not modelled.

5. **CH/VAT triangular transactions:** Transactions involving a third country (e.g., DE seller →
   CH intermediary → FR buyer) are out of scope.

6. **OSS (One Stop Shop) scheme:** Not applicable to B2B vehicle sales; only relevant for B2C
   digital services. Out of scope.
