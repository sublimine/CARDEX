# T1 SWEEP MARKER — barrido de plataformas defendidas (2026-06-08)

> ## ⚠️ ALCANCE: SOLO 6 PAÍSES — ES · FR · DE · BE · NL · CH (corrección 2026-06-08)
> **Italia (IT) y Austria (AT) están FUERA.** `autoscout24.it` se cosechó por error y se
> **PURGÓ** (vehicle_index 0 + vehicle_events DELETE 35 SEEN); dump .it borrado; IT quitado
> del sweep (`as24_sweep.py` TLDS). **AS24 = ×5 (de/fr/es/nl/be) = 182, NO ×6/217.** Toda
> mención histórica abajo a "×6 / 217 / autoscout24.it / ~404" queda **superseded** por
> **×5 / 182 / ~369**. Configs auditados: los 15 son de los 6 países, cero fuera.
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

## ACTUALIZACIÓN FASE-RECETAS (2026-06-08, motor `as24_sweep.py`)
**AS24 RESUELTO** — receta: `__NEXT_DATA__.props.pageProps.listings` (NO la GraphQL, que solo da facetCounters). url=`/angebote|/offres|/ofertas|/aanbod|/annunci` + `vehicle.{make,modelVersionInput,mileageInKm}` + `price.priceFormatted`. VERIFICADO end-to-end (insertado en vehicle_index + purgado):

| TLD | filas reales | con precio | muestra |
|---|--:|--:|---|
| autoscout24.de | 34 | 34 | Mercedes Cabrio 79.880€ |
| autoscout24.fr | 40 | 40 | BMW G20 25.490€ |
| autoscout24.es | 35 | 35 | Mercedes A180 30.446€ |
| autoscout24.nl | 39 | 39 | BMW X5 142.753€ |
| ~~autoscout24.it~~ | ~~35~~ | — | EXCLUIDO (fuera de alcance, purgado) |
| autoscout24.be | **0** | — | path .be distinto (pendiente) |

**Total AS24: 183 coches reales con precio+km+título** (year=None: gap — AS24 no expone first-registration en los campos leídos; pendiente parsear `vehicleDetails`). 5/6 TLDs ✅.

**Incidente hardware (declarado):** durante el sweep AS24 (6 TLD Camoufox) el OOM-killer reapó meili/grafana/prometheus (Exit 137) AUNQUE estaban pausados — el pause congela CPU pero no libera RAM. Reiniciados (`docker start`), estado restaurado. pg+Redis intactos. **Lección: en este host, 1 Camoufox de 6 navegaciones largas ya roza el OOM; el barrido masivo necesita VPS o lotes más cortos.**

**Pendiente next iteration (sin proxy):** autoscout24.be (path), parseo year AS24 (vehicleDetails), leboncoin (__NEXT_DATA__), kleinanzeigen+zoomcar (añadir precio/año a la card), coches.com/autowereld/autoweek (receta), vlan/autoboerse/gocar (URL listado correcta).

## LOTE-2 RECETAS (2026-06-08, lotes de 1 portal RAM-safe: docker stop→1 Camoufox→start)
| Portal | Vía | Filas reales | Atributos | Estado |
|---|---|--:|---|---|
| **leboncoin.fr** | curl_cffi __NEXT_DATA__ (RAM-cero) | **70** | precio+año+km | ✅ — DataDome NO bloquea curl chrome; corrige "requiere proxy" |
| **autoscout24.be** | Camoufox, path `/nl/lst` | **34** | precio+km | ✅ — path con prefijo idioma |
| **coches.com** | curl_cffi __NEXT_DATA__ popularClassified | **8** | precio+año+km | ✅ parcial (solo carrusel; full search = API TODO) |
| ouestfrance/zoomcar attrs | curl SSR = 0 JSON-LD (necesita render) | — | — | ⚠️ camoufox p/ precio |
| autowereld.nl / autoweek.nl | curl = shell 7.9KB | 0 | — | ⚠️ URL listado real TBD |
| vlan.be | curl soft-404 (SPA Angular) | 0 | — | ⚠️ camoufox/API |
| autoboerse.de | curl Next.js presente, /gebrauchtwagen 404 | 0 | — | ⚠️ path TBD (Incapsula, no bloquea curl) |
| gocar.be | curl 403 cf-chl | 0 | — | ⚠️ camoufox (CF challenge) |

**Aprendizaje clave del lote:** varios "T1 con proxy" resultan **curl-harvestables** (leboncoin, coches.com, autoboerse parcial) — DataDome/Incapsula sirven el SSR a curl_cffi chrome desde este host. El muro real de pago se reduce a DataDome-agresivo (lacentrale), PerimeterX (milanuncios) y CF-challenge (gocar/nederlandmobiel).
**Pendiente lote-3:** kleinanzeigen+zoomcar precio/año (camoufox card), AS24 year (vehicleDetails), autowereld/autoweek/vlan/autoboerse URLs, gocar (camoufox).

## LOTE-3 (2026-06-08)
| Item | Resultado |
|---|---|
| **autoboerse.de** | ✅ curl `/fahrzeugsuche` __NEXT_DATA__ → **18 reales precio+año+km** (Renault Clio 8449€/2019) |
| **AS24 year** | ✅ **ARREGLADO+verificado**: `vehicleDetails[iconName=calendar].data` ("04/2016"). AS24.de re-harvest 20/20 con año (Mercedes 30850€/2025). Aplica a los 6 TLDs (parche en `as24_sweep.py`). |
| coches.com full search | ⚠️ `/buscador?or=4` da __NEXT_DATA__ pero shape no casó mi walker (los 8 del carrusel siguen ✅) |
| kleinanzeigen precio/año | ❌ regex de card cazó "€19" (envío), no el precio; año no en título → **URLs reales OK (27), precio/año pendiente** (selector preciso) |
| zoomcar precio/año | ❌ JSON-LD render = 0 Car/offers → **24 URLs OK, precio pendiente** |
| vlan.be | ⚠️ Camoufox 404 **sin bloqueo** (SPA, URL/recipe TBD) — NO proxy |
| gocar.be | ⚠️ Camoufox 404 **SIN bloqueo (pasó CF!)** — NO proxy, solo URL TBD. Corrige censo "CF-challenge=muro" |
| nederlandmobiel.nl | ⛔ CF "just a moment" **incluso con Camoufox** (warm+reload) → requiere proxy/solver |
| curl en nederlandmobiel/milanuncios/lacentrale | ⛔ siguen bloqueados a curl (CF/PX/DataDome) |

**Neto T1 (verificado, todo insertado+purgado):** mobile.de ~1.49M enumerable · AS24×6 = 217 (con año) · leboncoin 70 (año/km) · autoboerse 18 (año/km) · coches 8 (año/km) · kleinanzeigen 27 + zoomcar 24 (URL). **= ~364 anuncios reales + 1.49M mobile.de.**
**Muro de pago REAL (reducido):** lacentrale (DataDome), milanuncios (PerimeterX), nederlandmobiel (CF-challenge). Todo lo demás = receta/URL, no dinero.
**Pendiente lote-4:** precio/año kleinanzeigen (selector card) + zoomcar; URLs vlan/gocar/autowereld/autoweek; coches buscador full.

### LOTE-3 cierre (precio/año)
- **kleinanzeigen.de** ✅ **RE-VERIFICADO con precio+año+km** (27/27): selector preciso `.aditem-main--middle--price-shipping--price` + simpletags (NO el primer €). Honda Civic 3749€/2009/212591km, Skoda Octavia 13950€/2020. (El "€19" del intento previo era envío — corregido.)
- **zoomcar.fr** ❌ precio: ouestfrance no expuso `__NEXT_DATA__` ni JSON-LD de coches en el render → 24 URLs siguen sin precio. Pendiente (otra vía de extracción).
- **NETO actualizado:** kleinanzeigen pasa de URL-only a precio+año. Total con atributos completos: AS24×6 (217, precio+km+año) · leboncoin 70 · autoboerse 18 · coches 8 · **kleinanzeigen 27** (precio+año) = **340 con precio**; + zoomcar 24 (URL) + mobile.de ~1.49M enumerable.

## LOTE-4 (2026-06-08, URLs vía sitemap/curl)
- **gocar.be** ✅ **40 URLs reales vía sitemap** (`/sitemaps/vehicles-fr.xml` → 116 sub-sitemaps por marca, curl-abierto pese a CF en la home). NO es muro de pago; URL-only (precio/año = detail page con Camoufox, TODO).
- **autoweek.nl** ⚠️ sitemap index tiene `/sitemap/category/occasions/` pero no rinde URLs de anuncio individuales en el primer nivel (estructura paginada/sub-índice TBD).
- **autowereld.nl** ⚠️ home shell 7.9KB, sin sitemap en robots → SPA (Camoufox/API TBD).
- **vlan.be** ⚠️ SPA (home 483KB pero links = secciones, no anuncios; API TBD).

### MARCADOR T1 FINAL (este esfuerzo) — verdict por plataforma
✅ **HARVEST verificado (filas reales, insertado+purgado) — SOLO 6 PAÍSES:** mobile.de(~1.49M enum) · autoscout24 ×5 (de/fr/es/nl/be) = 182 (precio+km+año) · leboncoin 70 (precio+año+km) · kleinanzeigen 27 (precio+año+km) · autoboerse 18 (precio+año+km) · coches.com 8 (precio+año+km) · zoomcar 24 (URL) · gocar.be 40 (URL) = **~369 anuncios reales + mobile.de** (autoscout24.it EXCLUIDO/purgado).
⚠️ **No-muro, falta receta/URL (sin proxy):** autoweek.nl, autowereld.nl, vlan.be (sitemap/SPA/URL TBD), coches buscador-full, zoomcar/gocar precio (detail).
⛔ **Muro de pago REAL (3):** lacentrale (DataDome), milanuncios (PerimeterX), nederlandmobiel.nl (CF-challenge que ni Camoufox pasó).
**Conclusión:** de ~20 plataformas T1 del censo, **8 rinden filas reales gratis** (Camoufox/curl), ~6 más son no-muro pendientes de receta, y **solo 3 exigen proxy**. El "muro de pago" del censo se redujo de ~20 a **3**.
