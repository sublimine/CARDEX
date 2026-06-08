---
name: project-discovery-scale
description: "Barrido discovery a escala (frente A) — rama feature/discovery-scale, dealers-con-web 28.570→45.864"
metadata: 
  node_type: memory
  type: project
  originSessionId: c2212611-b904-4b04-9c35-10a7aa492b10
---

Trabajo 2026-06-07 en worktree aislado `C:\Users\elias\projects\cardex-discovery-scale` (rama `feature/discovery-scale` desde main 6e0be32, **NO pusheado**, main intacto). Informe: `DISCOVERY_SCALE_REPORT.md`. Solo escribe `discovery_candidates`; dedup por índices únicos parciales `(domain,country)` y `(source,registry_id,country)` (NO migrar esquema).

**Métrica rectora = dealers CON WEB (dominio no-NULL = puente a inventario).** Resultado verificado: total 460.930→685.572; **con-web 28.570→45.864 (+17.294)**. Por país con-web: DE +10.078, NL +3.985, CH +2.633, ES +284, FR +249, BE +65.

**Conectores nuevos (todos endpoints curl-verificados, +73 tests, suite 1347 verde):**
- `fr_recherche_entreprises.py` (endurecido retry+throttle): FR 101 deptos NAF 45.11Z/45.19Z = 175K filas (sin web, registro).
- `ch_zefix_allcantons.py`: mirror Basel `data-bs.ch/.../all_cantons/companies_<KT>.csv`, 26 cantones, filtro trilingüe → 9.806.
- `oem_locators.py`: VW/Audi/Škoda/Toyota/Hyundai/Kia (VW SDS `oneapi.volkswagen.com` key pública; Kia keyword no lat/lng).
- `oem_wave2.py`: Renault/Dacia (`POST {dom}/wired/commerce/v2/dealers/locator`, dwsLink=web) + SEAT (SNW .snw.xml `url`, BE Dieteren) geo-sweep.
- `ch_agvs.py` (AGVS 1 GET, 3.223 con web ★), `de_gelbeseiten.py` (web base64 data-webseiteLink ★), `nl_bovag.py` (sitemap→/leden/ NEXT_DATA ★).
- `osm_expanded_run.py`: +env `OSM_COUNTRIES` para re-fetch por país.

**Bloqueado/backlog (no inventar):** Mercedes/Ford=Akamai; PSA Peugeot/Citroën/Opel=DNS muerto (wsrest.servicesgp.mpsa.com); Fiat=NPE Java; directorios BE/ES (GoudenGids/PáginasAmarillas)=Incapsula→navegador/proxy; 11880-DE(52K detalle) y PagesJaunes-FR→dedicar VPS, no martillear host compartido. H3/name-based Overpass=redundante (área ya exhaustiva). Amplía [[project-discovery-free-source-ceiling]].
