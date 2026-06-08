---
name: project_nl_vertical
description: Vertical NL validado (RDW discovery + inventario por portales); qué rinde y qué necesita E07; receta de fan-out
metadata: 
  node_type: memory
  type: project
  originSessionId: 3580463c-4ae4-408a-9d01-af8872ba2a62
---

Vertical NL clavado como patrón de referencia (rama `feature/p0-rewiring-canon`, ver `NL_VERTICAL_REPORT.md`). Complementa [[project_p0_execution_state]].

**Discovery RDW (nuevo, funciona):** `scrapers/discovery/sources/nl_rdw.py` — Socrata sin clave. Dataset `5k74-3jha` (Erkende Bedrijven: volgnummer/naam_bedrijf/dirección, **sin web**) + `nmwb-dqkz` (Erkenningen) join por `volgnummer`. **Filtro dealer:** `erkenning in (Bedrijfsvoorraad[24694], Handelaarskenteken[24887])` = dealers reales; excluye Fotograaf/Kentekenplaatfabrikant. Run vivo: 300 dealers upserted (capacidad ~24.7K). `RDW_LIMIT` para muestra. El shell SÍ alcanza opendata.rdw.nl (no hace falta proxy).

**Inventario (lo que RINDE coste-cero para NL):** PORTALES con JSON-LD vía el seam P0 — verificado E2E en `autotrack.nl` y `viabovag.nl` (vehicles 30→33, datos ricos reales, purgado). Harness: `scripts/verify_seam_redis.py --domain <portal> --country NL --limit N` (redis throwaway :56390). Otros portales NL JSON-LD: autoweek/autowereld/autokopen.

**Lo que NO rinde (verificado):** gaspedaal.nl = meta-agregador (`missing_critical`). **Dealer-sites directos** (nefkens/munsterhuis/etc.) = SPAs JS/XHR (Next.js, 0 `@type` Car en HTML estático, 92 hints xhr) → `generic_extractor` estático solo encuentra páginas-categoría, no detalles. Necesita **E07 playwright-XHR** (P1/P2). `scripts/verify_dealer_vertical.py` deja el dealer-path cableado y medible.

**A2 domain resolution:** `name_to_domain` (crt.sh:5432 ALCANZABLE, extendido a source rdw) pero lento (~10s/q) y bajo rendimiento en long-tail (0/10); DDG baneado. Vía recomendada para dominios = **locators OEM `?postcode=`** (devuelven web del dealer directo) o OSM (ya da dominio, 2913 NL).

**Fan-out (núcleo country-agnostic):** seam A6/A7 + engine + 18 identidades warmed sirven los 6 países. Replicar = config + source de discovery del país (CH→ch_zefix, FR→fr_sirene, DE→OSM+OffeneRegister...) + correr el seam sobre los portales del país (ya en PORTAL_REGISTRY) con `--country {cc}`. No requiere código nuevo del seam.

**Resiliencia config-driven + drift (seed, ver RESILIENCE_DRIFT_DESIGN.md):** receta de extracción por origen externalizada a store versionado `configs/portals/<source>.json` (`scrapers/portals/config.py::load`); `scrapers/intelligence/drift_gate.py` compone 3 dims (VOLUME+FIELD baselines nuevos + SCHEMA-fp reusando `intelligence/schema.py` D2 sobre `schema_registry`, que existía sin cablear). `evaluate()→DriftReport` nombra la dim rota → alerta por origen+causa → reparar = editar el JSON. Cableado en verify_seam_redis (demostrado vivo: schema_registry sellado). Migrar subclases a ejecutar-desde-config + cablear en coordinator = P1. Suite 1246 verde.
