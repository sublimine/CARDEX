# T1 SWEEP MARKER — barrido de plataformas defendidas (2026-06-08)
**Método:** 1 Camoufox secuencial (warm→search), extracción cascada (JSON-LD→regex), seam_writer validate-20-50-y-purga. Hardware: Meili/Grafana/Prometheus pausados durante el barrido; pg+Redis vivos; concurrencia 1. **Cifras VERIFICADAS** (inspeccionado el JSONL, no solo el contador).

## Hallazgo central
**El WAF NO es el cuello para la mayoría.** Camoufox **pasa (HTTP 200)** en 11 plataformas (Akamai + Cloudflare-Pro). El bloqueo real se reparte así:
- **Anti-bot vencido GRATIS (Camoufox 200):** mobile.de, kleinanzeigen.de, autoscout24×6, autowereld.nl, coches.com, autoweek.nl, ouestfrance/zoomcar.
- **Cuello real = receta de EXTRACCIÓN por portal** (SPA → API interna), NO dinero — salvo la minoría DataDome/PerimeterX/CF-challenge que sí exige proxy residencial.

## Marcador
| Plataforma | WAF | Camoufox | Anuncios reales | Estado | Config |
|---|---|---|--:|---|---|
| mobile.de | Akamai v3 | ✅200 | ~99% enumerable (964/min) | ✅ HARVEST (probado) | mobile.de.json |
| **kleinanzeigen.de** | Akamai v3 | ✅200 | **26 reales** (`/s-anzeige/…/<id>`) | ✅ HARVEST | kleinanzeigen.de.json |
| **zoomcar.fr** (vía ouestfrance-auto.com) | CF-Pro/Incapsula | ✅200 | **24 reales** (JSON-LD, `…-<id>.html`) | ✅ HARVEST | zoomcar.fr.json |
| autoscout24.de/fr/es/nl/be/it | Akamai v3 | ✅200 | 0 (SPA, sin SSR) | ⚠️ RECETA API (no proxy) | autoscout24.de.json |
| autowereld.nl | — | ✅200 | 0 (regex no casó) | ⚠️ RECETA | — |
| coches.com | CF-Pro | ✅200 | 0 (regex casó assets JS = falso+) | ⚠️ RECETA | coches.net.json |
| autoweek.nl | Akamai | ✅200 | 0 (solo páginas modelo) | ⚠️ RECETA | — |
| nederlandmobiel.nl | CF challenge | ⛔403 cf-chl | 0 | ⛔ BLOQUEADO (CF challenge) | — |
| promoneuve.fr | DataDome | ⛔404+datadome | 0 (coches nuevos) | ⛔ PROXY | — |
| vlan.be / autoboerse.de / zoomcar.fr(directo) / gocar.be | varios | 404 | — | ⚠️ INCONCLUSO (URL-objetivo mal) | — |
| lacentrale.fr | DataDome | ⛔ (agotado prior) | 0 | ⛔ PROXY RESIDENCIAL FR | lacentrale.fr.json |
| milanuncios.com | PerimeterX | ⛔ (agotado prior) | 0 | ⛔ PROXY RESIDENCIAL ES | milanuncios.com.json |

## Veredicto
- **Filas reales extraídas de plataformas defendidas: mobile.de (~99%), kleinanzeigen.de (26), zoomcar.fr (24).** Validadas en `vehicle_index` y purgadas (disciplina). Sin precio/año aún (extractor genérico = solo URL; falta parseo de card por portal).
- **~11 plataformas: Camoufox vence el WAF gratis; falta solo la receta de extracción** (AS24 SPA = API `as24-search-funnel`, etc.). Es ingeniería, no dinero.
- **Solo 4-5 exigen proxy de pago:** lacentrale, milanuncios (agotadas), nederlandmobiel (CF challenge), promoneuve (DataDome).
- **Pendiente honesto:** recetas por portal (AS24/coches/autowereld), URLs correctas (vlan/autoboerse/gocar), parseo precio/año, leboncoin (DataDome, curl 200 + __NEXT_DATA__ por probar).
