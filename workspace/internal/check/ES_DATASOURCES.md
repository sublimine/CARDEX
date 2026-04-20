# ES data sources — beyond plate lookup

The per-plate resolver ([`plate_es.go`](plate_es.go)) covers the three
public "plate → vehicle" paths documented in [ES_ENDPOINTS.md](ES_ENDPOINTS.md).
This file covers **bulk** public datasets that DGT publishes under the
"microdatos" programme — distributions we import once and query locally,
rather than calling per request.

Recorded: 2026-04-21.

## 1. MATRABA / TRANSFE / BAJAS — DGT monthly microdata

**What it is.** Monthly ZIP dumps of every vehicle event processed by
the DGT: matriculations (new registrations), transferencias (ownership
changes), and bajas (deregistrations — scrap, theft, export). Released
under the "Jefatura Central de Tráfico — Microdatos" portal since 2014.

**Why we ingest it.** The feed carries 69 technical fields per row —
including the ones `comprobarmatricula.com` does NOT expose: masa en
orden de marcha, Euro norm, CO₂, EU category code, electric range,
wheelbase, municipio INE, and the DGT homologation number
(`CONTRASENA_HOMOLOGACION`). Once the per-plate resolver has extracted
a VIN from CM, `matraba.Store.LookupByVIN` augments the PlateResult
with these fields — **without an extra network round-trip**.

### Distribution URL

Stable, public, no auth:

```
https://www.dgt.es/microdatos/salida/{YYYY}/{M}/vehiculos/{folder}/export_mensual_{prefix}_{YYYYMM}.zip
```

| Dataset   | Folder             | Prefix | Example URL                                                                                               |
|-----------|--------------------|--------|-----------------------------------------------------------------------------------------------------------|
| MATRABA   | `matriculaciones`  | `mat`  | https://www.dgt.es/microdatos/salida/2024/12/vehiculos/matriculaciones/export_mensual_mat_202412.zip      |
| TRANSFE   | `transferencias`   | `tra`  | https://www.dgt.es/microdatos/salida/2024/12/vehiculos/transferencias/export_mensual_tra_202412.zip       |
| BAJAS     | `bajas`            | `baj`  | https://www.dgt.es/microdatos/salida/2024/12/vehiculos/bajas/export_mensual_baj_202412.zip                |

**Publishing cadence.** The previous month's file lands ~15-30 days into
the following month. A 404 in the first weeks is not a fatal error —
the importer's `-skip-missing` flag (default on) treats it as
`ErrNotYetPublished` and continues.

### File format

- **Layout:** fixed-width, 714 chars per row, 69 fields. Full field
  offsets in [`matraba/record.go`](matraba/record.go).
- **Encoding:** ISO-8859-1 (Latin-1). Names like "CÁDIZ" / "ELCHE /
  ELX" / "A CORUÑA" decode to UTF-8 via the streaming decoder in
  [`matraba/parser.go`](matraba/parser.go) — no `golang.org/x/text`
  dependency, since Latin-1 is trivially 1:1 for codepoints 0x00-0xFF.
- **Line endings:** Windows (`\r\n`); the parser strips trailing CR.
- **Numeric sentinels:** `*****` and `-` mean "unknown". The parser
  normalises both to zero.
- **Dates:** all fields are DDMMYYYY; `00000000` means "unset".
- **Size:** ~300k-1M rows per monthly MATRABA dump (~50-80 MB ZIP,
  200-400 MB uncompressed). TRANSFE is similar; BAJAS is smaller.

### Privacy note — VIN masking (since 2025-02-01)

Starting with the **February 2025** release, DGT masks the final 10
chars of every VIN (`WVGZZZ5NZ**********`). The first 11 chars (WMI +
first 3 of VDS) survive. The parser's `Record.VINMasked()` /
`Record.VINPrefix()` helpers surface this cleanly; the store indexes
both `vin` (full) and `vin_prefix` (11 chars) so post-2025 data is
still usable for family-level enrichment.

For pre-2025-02 files the full VIN is available — exact matches are
possible back to the 2014-12 origin of the microdatos programme.

### Importer

```sh
# Single month
go run ./cmd/matraba-import -db data/workspace.db -year 2024 -month 12

# Range, one dataset
go run ./cmd/matraba-import -db data/workspace.db -from 2024-01 -to 2024-12

# Range, all three datasets
go run ./cmd/matraba-import -db data/workspace.db -from 2024-01 -to 2024-12 -all

# Preview URLs without downloading
go run ./cmd/matraba-import -year 2024 -month 12 -dry-run
```

ZIPs are cached under `./data/matraba-zips/`; re-running the importer
is idempotent. The SQLite tables (`matraba_vehicles`,
`matraba_imports`) are created by `matraba.EnsureSchema`.

### Wiring into the plate resolver

```go
db, _ := sql.Open("sqlite", dbPath)
_ = matraba.EnsureSchema(db)
store := matraba.NewStore(db)
registry := check.NewPlateRegistryWithOptions(rdwBase, cache, store)
```

With a non-nil store attached, `esPlateResolver.Resolve` calls
`enrichWithMATRABA` after the CM + DGT-badge pass. The merge is strictly
additive — CM data is preserved. Source string is extended with
`"DGT MATRABA (microdatos)"` when the lookup hits.

### Blocked / inferior alternatives considered

- **ANFAC mensual** (manufacturer-side new-registrations report) —
  aggregates to make/model, not per-vehicle. No plate or VIN.
- **Eurostat "veh_regis"** — EU-level counts by year/fuel/category.
  Zero per-vehicle identity.
- **INE — Parque de vehículos** — annual snapshot counts by province.
  Statistical only.
- **EU GDPR vehicle registers (EUCARIS)** — closed exchange between
  member-state authorities, not a public endpoint.
- **DGT informe-vehiculo** — per-plate, but requires Cl@ve / digital
  certificate (see ES_ENDPOINTS.md §3).

**Conclusion.** MATRABA/TRANSFE/BAJAS is the only public, free, no-auth
Spanish dataset carrying per-vehicle technical detail at VIN resolution.
Monthly ingestion + SQLite indexing is the right architecture: a single
lookup answers in <1 ms, no extra upstream dependency, and the feed is
stable enough that a monthly cron is sufficient.

---

## 2. AEAT — matriculation tax bracket (future)

The Agencia Tributaria publishes the mapping between engine/CO₂ and the
"Impuesto Especial sobre Determinados Medios de Transporte" bracket
(0/4.75/9.75/14.75%). Public, but distributed as annual PDFs rather
than a machine-readable feed. Low priority — the resolver doesn't
surface tax bracket today. If added later, it plugs into PlateResult
via a new optional column, not a new network call.

---

## Summary

| Source             | Scope                   | Freshness | Integration              |
|--------------------|-------------------------|-----------|--------------------------|
| comprobarmatricula | per-plate (rich)        | live      | plate_es.go (primary)    |
| DGT distintivo     | per-plate (badge)       | live      | plate_es.go (DGT fetch)  |
| plate_cache        | per-plate cache         | 30-day    | cache.go                 |
| **DGT MATRABA**    | **bulk, per-VIN**       | **monthly** | **matraba/ + plate_es_matraba.go** |
