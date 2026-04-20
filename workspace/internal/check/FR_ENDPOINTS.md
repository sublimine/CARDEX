# France — Plate Resolution Sources (investigation)

Probes run 2026-04-20. Test plate: `FX055SH` (valid post-2009 SIV plate; Dacia Sandero III 2021).
All responses captured under `/tmp/cardex_probes/fr_*`.

## ✅ immatriculation-auto.info — WORKS (primary source)

```
curl -s -A "Mozilla/5.0" https://www.immatriculation-auto.info/vehicle/FX055SH
→ HTTP 200, 29 KB Astro-rendered HTML
```

Reliable data in SSR HTML:

- `<title>FX055SH - DACIA 2021</title>` → plate, make, year
- `<meta name="description" content="DACIA SANDERO III immatriculée en France sous
  le numéro de plaque d'immatriculation FX055SH en 2021. Découvrez son carburant
  Essence, sa Manuelle et sa capacité de 999 cm³">`
  → make, model, year, fuel, transmission, displacement
- `<astro-island … props="{&quot;input&quot;:[0,&quot;FX055SH&quot;],
  &quot;brandModelYear&quot;:[0,{&quot;brand&quot;:[0,&quot;DACIA&quot;],
  &quot;model&quot;:[0,&quot;SANDERO III&quot;],&quot;year&quot;:[0,&quot;2021&quot;]}], …}">`
  → same brand/model/year in structured JSON (more robust than title parsing)

Not-found marker: page still returns HTTP 200 but the `<title>` contains
"Téléchargez l'application" instead of the plate.

Available fields from this source:
`Plate`, `Make`, `Model`, `FirstRegistration` (year only), `FuelType`,
`DisplacementCC`. No VIN, no mileage, no CO₂, no Euro norm, no colour.

## ❌ api.immatriculation-auto.info — Cloudflare + API-key wall

```
curl https://api.immatriculation-auto.info/vehicle/FX055SH
→ HTTP 403 "Access denied; API key required"
```

## ❌ data.gouv.fr — aggregate only

```
curl https://www.data.gouv.fr/api/1/datasets/?q=immatriculation
→ HTTP 200: 12 datasets of aggregated market-share CSVs (monthly totals
  by marque, département). No per-plate lookup.
```

## ❌ ADEME Car Labelling (carlabelling.ademe.fr)

Search UI is JS-rendered. Probed:
- `GET /` → SPA shell (8 KB) + `main.js` bundle.
- `POST /recherche/getvehicules` → returns literal `"0"` (uses `id_moteur`
  form state, not free-text plate/model).
- Bundle analysis: no per-plate endpoint, only filter-based comparator.

Not plate-queryable. Ignore.

## ❌ histovec.interieur.gouv.fr — requires owner credential

```
curl https://histovec.interieur.gouv.fr/
→ HTTP 200 SPA. Flow requires "numéro de formule" from the carte grise
  (11-digit private code held by the vehicle owner) + plate + date of birth.
```
Government design — prevents unauthenticated plate lookup by third parties.

## ❌ prix-carte-grise.info

```
curl https://www.prix-carte-grise.info/
→ curl: (6) Could not resolve host
```
Dead or blocks DNS to non-FR egress.

## ❌ vroomly.com / cartegrise.com

```
curl https://www.vroomly.com/carte-grise/...
→ HTTP 200 but returns generic marketing/quote form. No plate database.
curl https://www.cartegrise.com/
→ HTTP 200, administrative paperwork service. No lookup.
```

## Summary

Only source that returns real per-plate vehicle data without auth is
`immatriculation-auto.info` via its SSR HTML. Parse the `brandModelYear`
astro-island prop (most reliable) and fall back to `<title>` + meta description
for fuel/displacement.
