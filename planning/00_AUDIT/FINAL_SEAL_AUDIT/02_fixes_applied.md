# Wave 2 — Track 2 Legal/Regulatory: Fixes Applied

> **Branch:** `fix/wave2-track2-legal`
> **Date:** 2026-04-16
> **Mandate:** Autorización Salman / Política R1
> **Source audit:** `02_legal_regulatory.md` — 14 claims scored, 2 INCORRECT, 5 ACTION

---

## Summary

| Category | Count |
|---|---|
| Incorrect claims corrected | 2 |
| AI Act Art. 50(2) implementation | 1 end-to-end feature (struct + validator + terminal UI) |
| Integration tests added | 12 (7 unit + 5 integration) |
| Planning docs created | 3 |
| Planning docs updated | 2 |
| Go packages created | 1 (`cardex.eu/quality/internal/nlg`) |
| Go files modified | 3 |
| Race-detector test result | **PASS** — 21/21 packages green |

---

## Finding Register

| # | Finding | Severity | Action | Commit | Files | Test |
|---|---|---|---|---|---|---|
| F-01 | DSA Art. 45 cited as CARDEX obligation — incorrect (Art. 45 = VLOP codes of conduct) | CRITICAL | Replaced with correct Arts. 9/11/14/27 obligation table | `bb6a197` | `planning/02_MARKET_INTELLIGENCE/04_REGULATORY_FRAMEWORK.md` §I.4 | n/a (planning doc) |
| F-02 | E11 legal basis cited as "EU Data Act Art. 4/5" — incorrect (Data Act covers IoT/connected hardware, not web platform listings) | CRITICAL | Replaced with GDPR Art. 6(1)(a)/(b) dual-anchor + 6-step consent flow table | `bb6a197` | `planning/02_MARKET_INTELLIGENCE/04_REGULATORY_FRAMEWORK.md` §IV.5, `planning/04_EXTRACTION_PIPELINE/strategies/E11_dealer_edge_onboarding.md` §3 | n/a (planning doc) |
| F-03 | AI Act Art. 50(2) compliance: no machine-readable `is_ai_generated` marker existed | CRITICAL | Implemented `AIGeneratedMetadata` struct + `Validate()` + `PromptHash()` in new `nlg` package | `2fc5eea` | `quality/internal/nlg/aiact.go` | `quality/internal/nlg/aiact_test.go` (7 unit tests) |
| F-04 | V11 NLG Quality validator did not check AI Act disclosure | CRITICAL | Added CRITICAL check: if `AIGeneratedMeta != nil` and `Validate()` fails → block publication | `2fc5eea` | `quality/internal/validator/v11_nlg_quality/v11.go` | `quality/internal/validator/v11_nlg_quality/v11_aiact_test.go` (5 integration tests) |
| F-05 | `Vehicle` struct had no field for AI-generated metadata | HIGH | Added `AIGeneratedMeta *nlg.AIGeneratedMetadata` to `pipeline.Vehicle` | `2fc5eea` | `quality/internal/pipeline/validator.go` | Covered by V11 integration tests |
| F-06 | Terminal `cardex show` rendered no AI-generated indicator | MEDIUM | Added `[AI]` badge (lipgloss colour 220) + model/lang dim info to `runShow` | `ea109a1` | `frontend/terminal/cmd/cardex/main.go` | Build green |
| F-07 | VG Bild-Kunst (C-392/19) post-Svensson nuance missing from regulatory framework | MEDIUM | Added note: framing with anti-framing tech-measures = communication to new public; permanent product constraint on iframes | `2a260f4` | `planning/02_MARKET_INTELLIGENCE/04_REGULATORY_FRAMEWORK.md` §III.2 | n/a (planning doc) |
| F-08 | No documented mitigations for Innoweb-style sui generis litigation (C-202/12) | HIGH | Created full mitigation doc: no real-time relay, 5 000 rec/source/day cap, ≥ 1 500 ms delay, ETL transform, volume logging, PR change-gate checklist | `097576f` | `planning/06_ARCHITECTURE/05_LITIGATION_MITIGATION.md` | n/a (planning doc) |
| F-09 | No T&Cs or privacy notice clause for AI Act Art. 50(2) disclosure | HIGH | Created disclosure planning doc with exact T&Cs §[X] wording, privacy notice paragraph, evidence trail table, dealer override flow, authority request SLA | `097576f` | `planning/02_MARKET_INTELLIGENCE/05_AIACT_DISCLOSURE_TERMS.md` | n/a (planning doc — requires legal review before prod) |

---

## Test Results

```
cd quality && GOWORK=off go test -race ./...

ok  cardex.eu/quality/internal/nlg                         2.022s
ok  cardex.eu/quality/internal/validator/v01_vin_checksum  2.972s
ok  cardex.eu/quality/internal/validator/v02_nhtsa_vpic    5.295s
ok  cardex.eu/quality/internal/validator/v03_dat_codes     3.158s
ok  cardex.eu/quality/internal/validator/v04_nlp_makemodel 3.092s
ok  cardex.eu/quality/internal/validator/v05_image_quality 5.240s
ok  cardex.eu/quality/internal/validator/v06_photo_count   2.981s
ok  cardex.eu/quality/internal/validator/v07_price_sanity  2.986s
ok  cardex.eu/quality/internal/validator/v08_mileage_sanity 3.074s
ok  cardex.eu/quality/internal/validator/v09_year_consistency 2.964s
ok  cardex.eu/quality/internal/validator/v10_source_url_liveness 5.303s
ok  cardex.eu/quality/internal/validator/v11_nlg_quality   1.840s
ok  cardex.eu/quality/internal/validator/v12_cross_source_dedup 3.042s
ok  cardex.eu/quality/internal/validator/v13_completeness  2.925s
ok  cardex.eu/quality/internal/validator/v14_freshness     2.595s
ok  cardex.eu/quality/internal/validator/v15_dealer_trust  2.619s
ok  cardex.eu/quality/internal/validator/v16_photo_phash   4.080s
ok  cardex.eu/quality/internal/validator/v17_sold_status   3.972s
ok  cardex.eu/quality/internal/validator/v18_language_consistency 2.451s
ok  cardex.eu/quality/internal/validator/v19_currency      2.422s
ok  cardex.eu/quality/internal/validator/v20_composite     2.460s

21 packages: 21 PASS, 0 FAIL, 0 RACE
```

```
cd frontend/terminal && GOWORK=off go build ./...  → exit 0
```

---

## Commits (chronological)

| Commit | Message |
|---|---|
| `bb6a197` | fix(legal): correct DSA Art.45 ref + rewrite E11 base legal to GDPR Art.6(1)(a)/(b) |
| `2fc5eea` | feat(ai-act): implement Art.50(2) AIGeneratedMetadata + V11 disclosure check |
| `ea109a1` | feat(terminal): AI Act Art.50(1) visible [AI] badge in cardex show command |
| `2a260f4` | docs(legal): add VG Bild-Kunst C-392/19 post-Svensson nuance + iframe prohibition |
| `097576f` | docs(legal): Innoweb litigation mitigations + AI Act T&Cs disclosure spec |
| *(this file)* | `docs(wave2): 02_fixes_applied.md appendix — 9 findings, all resolved` |

---

## Open Items (not in Wave 2 scope)

| Item | Status |
|---|---|
| Legal counsel review of T&Cs §[X] wording | Pending — external |
| Implement `nlg_metadata` sidecar DB table | Pending — Sprint 25 |
| Web UI `[AI]` badge | Pending — Sprint 25 (frontend web) |
| Dealer portal "disable AI generation" toggle | Pending — Sprint 26 |
| Production deployment before 2 Aug 2026 deadline | Required |
