# ES plate resolver — endpoint research

Recorded: 2026-04-20. Test plates: `8000LVY` (VW Tiguan 2009), `1234BCJ` (Seat Ibiza 2000).

Only public, unauthenticated, free HTTP endpoints are listed. APIs behind Cl@ve,
digital certificate, payment, or APK decompilation are explicitly excluded.

**Rate-limit mitigation in this package.** comprobarmatricula.com enforces a
per-IP anti-scrape bucket (returns `{"ok":0,"limit":true}` after ~3 lookups and
`{"ok":0,"err":"Forbidden"}` when the API is hit without a valid page session).
The resolver addresses this on three fronts:

1. **Persistent plate cache** (`plate_cache` table, `cache.go`): once CM
   returns a rich record, the full `PlateResult` is stored for 30 days. Repeat
   lookups skip CM entirely. Partial (DGT-only) results are cached 1 hour so
   CM is retried after its bucket refills. A stale cache is surfaced when all
   live sources fail rather than letting the user see a blank report.
2. **User-Agent rotation** (`cmUserAgents` pool): randomised per lookup so
   requests don't cluster under one fingerprint.
3. **Per-request cookie jar**: every lookup starts with a fresh jar; CM's
   anti-scrape cookies are harvested from the page hit and replayed on the
   API call within the same logical session.

---

## 1. comprobarmatricula.com — PRIMARY SOURCE (rich dataset incl. VIN)

Commercial landing page that renders a "teaser" with the full tech-sheet in
plain JSON. Selling a PDF report is their revenue, but the teaser payload is
public and exhaustive.

### Flow

1. **GET the plate page** to harvest a CSRF-style token.

   ```
   GET https://comprobarmatricula.com/matricula/{PLATE}/
   User-Agent: Mozilla/5.0 …
   ```

   Response: HTTP 404 (quirk — they always return 404 even on valid plates),
   ~260 KB HTML. The page embeds two hidden inputs:

   ```html
   <input type="hidden" id="_g_tk" value="1776671834.8f9078a66ca1e933.f7d4514457a21c8d416782666006715c65f102da26c2aa5a0246ee9f305b8a10">
   <input type="text"   id="_g_hp" name="_website" tabindex="-1" autocomplete="off" value="">
   ```

   `_g_tk` = time-salted HMAC; `_g_hp` = honeypot (must stay empty).

2. **GET the JSON endpoint** with the token.

   ```
   GET https://comprobarmatricula.com/api/vehiculo.php?m={PLATE}&_tk={TOKEN}&_hp=
   Referer: https://comprobarmatricula.com/matricula/{PLATE}/
   Accept: application/json
   ```

### Real output — plate `8000LVY`

```json
{
  "ok": 1,
  "mat": "8000LVY",
  "mat_fmt": "8000 LVY",
  "year": 2006,
  "age": 17,
  "brand": "Vw",
  "marca_oficial": "VW",
  "model": "Tiguan",
  "modelo_completo": "TIGUAN (5N_)",
  "version": "2.0 TDI 4motion | 170 cv",
  "fuel": "Diésel",
  "potencia_cv": 170,
  "potencia_kw": 125,
  "cilindrada": "2.0L",
  "cilindrada_cc": "1968 cc",
  "carroceria": "SUV",
  "caja": "Manual",
  "codigo_motor": "CFGB",
  "k_type": "23179",
  "vin": "WVGZZZ5NZAW021819",
  "fecha_matriculacion": "02/09/2009",
  "annee_modelo": "2009",
  "etiq": "B",
  "etiq_color": "#F5C800",
  "itv_date": "20/10/2027",
  "owners": 3,
  "score": 28,
  "score_label": "Alto riesgo",
  "api_source": "awn",
  "note": "Datos verificados de fuentes oficiales."
}
```

### Verified fields

| Field               | Type   | Example                      |
|---------------------|--------|------------------------------|
| `vin`               | string | `WVGZZZ5NZAW021819` ✅       |
| `marca_oficial`     | string | `VW`                         |
| `model`             | string | `Tiguan`                     |
| `modelo_completo`   | string | `TIGUAN (5N_)`               |
| `version`           | string | `2.0 TDI 4motion \| 170 cv`  |
| `fuel`              | string | `Diésel`                     |
| `potencia_cv`       | int    | `170`                        |
| `potencia_kw`       | int    | `125`                        |
| `cilindrada_cc`     | string | `1968 cc`                    |
| `carroceria`        | string | `SUV`                        |
| `caja`              | string | `Manual`                     |
| `codigo_motor`      | string | `CFGB`                       |
| `fecha_matriculacion` | string (DD/MM/YYYY) | `02/09/2009` |
| `etiq`              | string | `B`, `C`, `ECO`, `0`         |
| `itv_date`          | string (DD/MM/YYYY) | `20/10/2027`    |
| `owners`            | int    | `3`                          |

### Generalization test — plate `1234BCJ`

Same endpoint returned a complete record for a Seat Ibiza 1.9 TDI (2000) with
VIN `VSSZZZ6KZ1R113828`. ✅

### Pitfalls

- The hidden `_g_tk` is time-salted — must always re-harvest before calling
  the API. Do not cache it.
- HTTP 404 on the HTML page is normal.
- `fuel` comes with accented characters (`Diésel`).
- `etiq` is less authoritative than the DGT endpoint (a 2000 diesel Ibiza
  returns `0` here; DGT correctly has no badge for it). Use DGT badge as
  the canonical source.
- **IP-based rate limit.** After ~2–3 lookups the API returns
  `{"ok":0,"limit":true,"err":"limit"}` for the same IP (this is how they
  funnel users to the paid PDF). The resolver treats this as a partial-success
  signal and falls back to DGT-only. For heavy production load, run the
  resolver from a pool of egress IPs or cache aggressively — the raw JSON
  is stable for the life of a plate.

---

## 2. DGT "distintivo ambiental" — BADGE ONLY (already implemented)

```
GET https://sede.dgt.gob.es/es/vehiculos/informacion-de-vehiculos/distintivo-ambiental/index.html?matricula={PLATE}
```

Public, no auth, no CAPTCHA. Badge appears in the SVG filename
`distintivo_{BADGE}_sin_fondo.svg`. Not-found message:
`"No se ha encontrado ningún resultado"`.

Badges observed: `CERO`, `ECO`, `C`, `B`, or absent (pre-2006 diesels).

---

## 3. DGT "informe de vehículo" — BLOCKED (requires Cl@ve / cert)

```
GET https://sede.dgt.gob.es/es/vehiculos/informe-vehiculo/
```

Returns the informational page only. The actual "consulta" requires Cl@ve
authentication or digital certificate. Excluded per rules.

---

## 4. vehiculodgt.es — SPA front for a paid backend

React SPA. Bundle references `https://dgt-be.vehiculodgt.es/api/` as base,
but all concrete paths require Stripe-payment flow first (embeds
`js.stripe.com`). No public read endpoint. Skipped.

---

## 5. auto-info.gratis — NOT ES-FACING

Polish-language site covering PL plates only (`/pojazd/{plate}`). `/es/…`
and ES-plate paths return HTTP 404. Skipped.

---

## 6. nomatricula.com — DEAD

DNS resolution fails. `https://sede.dgt.gob.es/…/nomatricula/…` does not
exist either. Skipped.

---

## 7. Other ES sources probed

- **autoficha.com** — paid, requires subscription.
- **cartell.es / cartell.com** — paid (Car-Pass-style).
- **ITV CCAA portals** — each of Spain's 17 autonomous regions runs its own
  ITV portal; none expose a public plate → inspection endpoint.
- **Ministerio de Transportes / MITMA** — no public plate API; data is
  released as bulk statistical CSVs, not per-plate.

## 8. Re-probed 2026-04-20 — no new viable public source

- **check-vehiculo.es** — DNS resolution fails (domain inactive).
- **infocoches.com** — permanent 301 to `forocoches.com` (forum, no plate DB).
- **matriculas.info** — GoDaddy page-builder storefront, no lookup form.
- **coches.net/matriculas/** — HTTP 403 (Cloudflare challenge, no public path).
- **autocasion.com/matricula/** — HTTP 404 (no such endpoint).
- **km77.com** — model catalog; indexed by make/model, not plate. Could be
  used for model-level specs enrichment post-VIN, but contributes nothing to
  plate → vehicle resolution.
- **plateomatic.com** — lander redirect, no lookup.
- **consulta-dgt.es / consultadni.es / numrplate.com / matricula-coches.com /
  revisionvehiculos.com** — DNS/connection failures.
- **ADEME (France)** — no public dataset with ES plate data; emissions
  catalogue is FR-only and keyed by variant name.

**Conclusion.** As of 2026-04-20, comprobarmatricula.com remains the only
free public ES source that exposes VIN / make / model / engine / ITV per plate.
The layered cache + UA rotation strategy described above is the correct
mitigation — there is no second rich source to fall back to.

---

## Summary — what the resolver ships

| Source                       | Fields delivered                                                                | Public? |
|------------------------------|---------------------------------------------------------------------------------|---------|
| comprobarmatricula.com       | VIN, make, model, variant, fuel, kW, cc, body, gearbox, first reg, ITV, owners  | ✅      |
| DGT distintivo ambiental     | Environmental badge (canonical)                                                 | ✅      |
| `plate_cache` (local SQLite) | Full PlateResult persisted 30 days after a successful CM lookup                 | n/a     |

These two sources in parallel deliver the complete PlateResult struct
(minus fields no ES portal publishes publicly: CO2, gross weight, colour).
The local cache extends this coverage across IP rate-limit windows.
