# TRACK 1 — CODE & DOCUMENTATION COHERENCE AUDIT

**Autorización:** Salman · **Política:** R1 (cero atajos) · **Fecha:** 2026-04-16  
**Rama:** `audit/track-1-code-docs` · **Auditor:** Claude Sonnet 4.6  
**Sprint activo:** Sprint 24 (no mezclado)

---

## Resumen ejecutivo

La auditoría revela **tres clases de brecha sistémica** que comprometen la trazabilidad planning↔código. (1) Las estrategias E10, E11 y E12 están **semánticamente intercambiadas** entre `planning/` y código: planning asigna E11=Edge/E12=Manual, el código implementa E11=Manual/E12=Edge, con la prioridad de E12 disparada de 0 a 1500. (2) **16 de 20 validadores** (V05–V19) tienen nombres completamente distintos entre planning y directorios de código, resultado de un desarrollo paralelo sin sincronización. (3) `README.md` y `ARCHITECTURE.md` afirman que `RobotsChecker` está "wired in all HTTP crawl paths" pero el tipo **no existe** en ningún archivo Go — la responsabilidad recae en el caller sin infraestructura centralizada. E13 (VLM), E10 real (Mobile API), las fases completas de E11/E12, y la fórmula Bayesiana del confidence scorer son deuda declarada como Phase 4/Sprint 8+. Policy R1 está limpia: cero stealth plugins, cero proxies residenciales, CardexBot/1.0 consistente.

---

## Tabla de hallazgos

> **Leyenda severidad:** CRITICAL = rompe contratos, claim falso o riesgo legal/operacional inmediato · HIGH = divergencia funcional documentada que causa bugs silenciosos · MEDIUM = inconsistencia de documentación o implementación incompleta declarada · LOW = discrepancia menor o pendiente de verificación

| # | SEVERITY | CATEGORÍA | DESCRIPCIÓN | ARCHIVO | LÍNEA |
|---|----------|-----------|-------------|---------|-------|
| 1 | CRITICAL | RobotsChecker ghost | README:75 afirma "`RobotsChecker` is wired in all HTTP crawl paths." El tipo **no existe** en código (grep cero hits). `browser.go:18` dice explícitamente "robots.txt compliance is the caller's responsibility." | `README.md:75` vs `discovery/internal/browser/browser.go:18` | 75 / 18 |
| 2 | CRITICAL | RobotsChecker ghost (ARCHITECTURE) | `ARCHITECTURE.md:172` repite el claim: "`RobotsChecker` verifies robots.txt compliance before crawling any URL." Mismo tipo inexistente. | `ARCHITECTURE.md:172` | 172 |
| 3 | CRITICAL | E11↔E12 swap — nombres | Planning `INTERFACES.md:30-31` declara dirs `e11_edge_onboarding/` y `e12_manual_review/`. Código real: `extraction/internal/extractor/e11_manual/` y `e12_edge/`. Completamente intercambiados. | `planning/04_EXTRACTION_PIPELINE/INTERFACES.md:30-31` vs `extraction/internal/extractor/` | 30–31 |
| 4 | CRITICAL | E12 prioridad 0→1500 | Planning `INTERFACES.md:253`: `PriorityE12 = 0 // Manual review`. Código `strategy.go:22`: `PriorityE12 = 1500 // Edge push — dealer-signed, highest trust`. Delta: +1500 (máxima prioridad en lugar de mínima). | `planning/.../INTERFACES.md:253` vs `extraction/internal/pipeline/strategy.go:22` | 253 / 22 |
| 5 | CRITICAL | E11 prioridad semántica | Planning `INTERFACES.md:252`: `PriorityE11 = 100 // Edge onboarding`. Código `strategy.go:33`: `PriorityE11 = 100 // Manual review queue`. El valor coincide pero la semántica es opuesta: en planning 100=Edge, en código 100=Manual. | `INTERFACES.md:252` vs `strategy.go:33` | 252 / 33 |
| 6 | CRITICAL | E10 estrategia errónea | Planning `E10_mobile_app_api.md` especifica APK analysis, Play Store/App Store reverse engineering, `apktool`, `gplaycli`, endpoint discovery. Código `e10_email/email.go:1-3` implementa **Email-Based Inventory** (CSV/Excel por email). Estrategias completamente distintas. | `planning/.../E10_mobile_app_api.md:1` vs `extraction/internal/extractor/e10_email/email.go:1` | 1 / 1 |
| 7 | CRITICAL | E10 prioridad 200→600 | Planning `INTERFACES.md:251`: `PriorityE10 = 200`. Código `strategy.go:32`: `PriorityE10 = 600`. Triple. | `INTERFACES.md:251` vs `strategy.go:32` | 251 / 32 |
| 8 | CRITICAL | E13 no implementado | Planning `E13_vlm_screenshot_extraction.md` (~227 líneas) especifica VLM inference (Phi-3.5/LLaVA/Qwen2-VL/InternVL2), ONNX runtime, screenshot tiling, prompt multilingual, post-processing. **Cero código en** `extraction/internal/extractor/`. No existe ningún directorio `e13*`. | `planning/.../E13_vlm_screenshot_extraction.md` vs `extraction/internal/extractor/` | — |
| 9 | CRITICAL | CONTRIBUTING path incorrecto | `CONTRIBUTING.md:22` dice: "Follow the same pattern ... in `extraction/internal/strategy/e{NN}_{name}/`". El directorio real es `extraction/internal/extractor/e{NN}_{name}/`. Todo colaborador nuevo crearía el paquete en la ruta equivocada. | `CONTRIBUTING.md:22` | 22 |
| 10 | CRITICAL | V05 nombre/función swap | Planning `V05_image_classification_ml.md`: "Inferir Make/Model/Year desde foto con YOLOv8n ONNX." Código dir: `v05_image_quality/` (resolution, blur, NSFW). Función completamente distinta. | `planning/.../V05_image_classification_ml.md:1` vs `quality/internal/validator/v05_image_quality/` | — |
| 11 | CRITICAL | V06 nombre/función swap | Planning `V06_identity_convergence.md`: "VIN+título+imagen→mismo coche." Código dir: `v06_photo_count/` (threshold mínimo de fotos). Función completamente distinta. | `planning/.../V06_identity_convergence.md:1` vs `quality/internal/validator/v06_photo_count/` | — |
| 12 | CRITICAL | V07 nombre/función swap | Planning `V07_image_quality.md`: "Resolución, blur, NSFW." Código dir: `v07_price_sanity/` (price range validation). Función completamente distinta. | `planning/.../V07_image_quality.md` vs `quality/internal/validator/v07_price_sanity/` | — |
| 13 | CRITICAL | V08 nombre/función swap | Planning `V08_image_phash_dedup.md`: "Perceptual hash distance ≤4 para deduplicación." Código dir: `v08_mileage_sanity/`. Función completamente distinta. | `planning/.../V08_image_phash_dedup.md` vs `quality/internal/validator/v08_mileage_sanity/` | — |
| 14 | HIGH | V09 nombre/función swap | Planning `V09_watermark_logo_detection.md`: "AI visual watermark detection." Código dir: `v09_year_consistency/` (year range check). | `planning/.../V09_watermark_logo_detection.md` vs `v09_year_consistency/` | — |
| 15 | HIGH | V10 nombre/función swap | Planning `V10_vehicle_binary_classifier.md`: "Non-vehicle image filter (YOLOv8)." Código dir: `v10_source_url_liveness/` (HTTP HEAD check). | `planning/.../V10_vehicle_binary_classifier.md` vs `v10_source_url_liveness/` | — |
| 16 | HIGH | V11 nombre/función swap | Planning `V11_mileage_sanity.md`: "Mileage range validation." Código dir: `v11_nlg_quality/` (NLG text quality). | `planning/.../V11_mileage_sanity.md` vs `v11_nlg_quality/` | — |
| 17 | HIGH | V12 nombre/función swap | Planning `V12_year_registration_consistency.md`: "Year vs registration date." Código dir: `v12_cross_source_dedup/` (fingerprint collision). | `planning/.../V12_year_registration_consistency.md` vs `v12_cross_source_dedup/` | — |
| 18 | HIGH | V13 nombre/función swap | Planning `V13_price_outlier_detection.md`: "Statistical outlier detection." Código dir: `v13_completeness/` (required fields). | `planning/.../V13_price_outlier_detection.md` vs `v13_completeness/` | — |
| 19 | HIGH | V14 nombre/función swap | Planning `V14_vat_mode_detection.md`: "Gross/net VAT detection." Código dir: `v14_freshness/` (listing age). | `planning/.../V14_vat_mode_detection.md` vs `v14_freshness/` | — |
| 20 | HIGH | V15 nombre/función swap | Planning `V15_currency_normalization.md`: "EUR conversion." Código dir: `v15_dealer_trust/` (reputation score). | `planning/.../V15_currency_normalization.md` vs `v15_dealer_trust/` | — |
| 21 | HIGH | V16 nombre/función swap | Planning `V16_cross_source_convergence.md`: "Multi-dealer dedup." Código dir: `v16_photo_phash/` (perceptual hash). | `planning/.../V16_cross_source_convergence.md` vs `v16_photo_phash/` | — |
| 22 | HIGH | V17 nombre/función swap | Planning `V17_geolocation_validation.md`: "Country consistency." Código dir: `v17_sold_status/` (HTTP 410 + keywords). | `planning/.../V17_geolocation_validation.md` vs `v17_sold_status/` | — |
| 23 | HIGH | V18 nombre/función swap | Planning `V18_equipment_normalization.md`: "Parts/features normalization." Código dir: `v18_language_consistency/` (lang vs country). | `planning/.../V18_equipment_normalization.md` vs `v18_language_consistency/` | — |
| 24 | HIGH | V19 nombre/función swap | Planning `V19_nlg_description_generation.md`: "AI text synthesis." Código dir: `v19_currency/` (price validity). | `planning/.../V19_nlg_description_generation.md` vs `v19_currency/` | — |
| 25 | HIGH | E05 prioridad incorrecta | Planning `INTERFACES.md:244` + `E05_dms_hosted_api.md:11`: `PriorityE05 = 1050`. Código `strategy.go:26`: `PriorityE05 = 950`. Delta: -100. | `INTERFACES.md:244` vs `strategy.go:26` | 244 / 26 |
| 26 | HIGH | E06 prioridad incorrecta | Planning `INTERFACES.md:247`: `PriorityE06 = 800`. Código `strategy.go:28`: `PriorityE06 = 850`. Delta: +50. | `INTERFACES.md:247` vs `strategy.go:28` | 247 / 28 |
| 27 | HIGH | E07 prioridad incorrecta | Planning `INTERFACES.md:248`: `PriorityE07 = 700`. Código `strategy.go:29`: `PriorityE07 = 800`. Delta: +100. | `INTERFACES.md:248` vs `strategy.go:29` | 248 / 29 |
| 28 | HIGH | E08 prioridad incorrecta | Planning `INTERFACES.md:250`: `PriorityE08 = 300`. Código `strategy.go:30`: `PriorityE08 = 700`. Delta: +400. | `INTERFACES.md:250` vs `strategy.go:30` | 250 / 30 |
| 29 | HIGH | E09 prioridad incorrecta | Planning `INTERFACES.md:249`: `PriorityE09 = 400`. Código `strategy.go:31`: `PriorityE09 = 700`. Delta: +300. | `INTERFACES.md:249` vs `strategy.go:31` | 249 / 31 |
| 30 | HIGH | E10 stub — Phase 4 | `e10_email/email.go:19-21`: "This sprint delivers the skeleton ... The real IMAP poller and staging table wiring are Phase 4 work." E10 no es funcional en producción. | `extraction/internal/extractor/e10_email/email.go:19` | 19–21 |
| 31 | HIGH | E10 Extract() stub | `e10_email/email.go:41`: "Implement with a real DB-backed reader in Phase 4." El método `Extract()` es un stub que devuelve error si no hay staging rows. | `extraction/internal/extractor/e10_email/email.go:41` | 41 |
| 32 | HIGH | E11 gRPC no implementado | `E11_dealer_edge_onboarding.md` especifica cliente Tauri, OAuth2 PKCE, DSA, DMS connectors (EasyCar, DealerPoint, SalesPoint). `e11_manual/manual.go:25-28`: Sprint 18 skeleton; "wired in main.go Phase 4." Los DMS connectors y el flujo DSA no existen. | `planning/.../E11:59-84` vs `e11_manual/manual.go:25` | 25 |
| 33 | HIGH | E12 gRPC server stub | `e12_edge/edge.go:16-25`: "Sprint 18 skeleton ... middleware is Phase 4 work." El gRPC server real, autenticación y wiring con main.go son futuros. | `extraction/internal/extractor/e12_edge/edge.go:16` | 16–25 |
| 34 | HIGH | E12 noOpStore en producción | `e12_edge/edge.go:62`: `noOpStore` es el store default "until the gRPC server is wired (Phase 4)". En producción, E12 no persiste nada. | `extraction/internal/extractor/e12_edge/edge.go:62` | 62 |
| 35 | HIGH | INTERFACES.md dirs incorrectos | `INTERFACES.md:30-31` declara `e11_edge_onboarding/` y `e12_manual_review/`. Los dirs reales son `e11_manual/` y `e12_edge/`. El spec de interfaces está desactualizado. | `planning/.../INTERFACES.md:30-31` | 30–31 |
| 36 | HIGH | E04 prioridad inconsistente | Planning `INTERFACES.md:246`: `PriorityE04 = 900`. Código `strategy.go:27`: `PriorityE04 = 900`. ✓ Coincide. (Registrado para completitud de la matrix de 12 estrategias.) | — | — |
| 37 | MEDIUM | ARCHITECTURE E10/E11/E12 swapped | `ARCHITECTURE.md:28-30`: "E10 Email/EDI · E11 Manual queue · E12 Edge stub". Planning: E10=Mobile, E11=Edge, E12=Manual. ARCHITECTURE coincide con código, no con planning. | `ARCHITECTURE.md:28` | 28–30 |
| 38 | MEDIUM | CONTEXT_FOR_AI E12 descripción | `CONTEXT_FOR_AI.md:54`: "E12 Edge stub (future edge client)". Código `e12_edge/edge.go` es más que un stub (proto definido, server parcial). Descripción minimiza el alcance real. | `CONTEXT_FOR_AI.md:54` | 54 |
| 39 | MEDIUM | E13 declarado como "Sprint 8+" | Planning `E13_vlm_screenshot_extraction.md:1-6`: "Estado: DOCUMENTADO — implementación Sprint 8+". Sin código. README/ARCHITECTURE no mencionan E13. Gap de trazabilidad. | `planning/.../E13:1` | 1–6 |
| 40 | MEDIUM | E11 outreach workflow ausente | Planning `E11:35-50` especifica email templates DE/FR/ES/NL, follow-up cadence 3-5-14 días, tracking en KG. Cero implementación en código. | `planning/.../E11:35-50` | 35–50 |
| 41 | MEDIUM | E11 DMS connectors ausentes | Planning `E11:59-61` especifica connectors para EasyCar, DealerPoint, SalesPoint. No existe ningún archivo de connector. | `planning/.../E11:59` | 59–61 |
| 42 | MEDIUM | E11 DSA UI ausente | Planning `E11:71-84` especifica Data Sharing Agreement UI, firma electrónica, consent management (GDPR Art. 6(1)(a)). No implementado. | `planning/.../E11:71` | 71–84 |
| 43 | MEDIUM | E12 reviewer dashboard ausente | Planning `E12:36-57` especifica dashboard web para revisores con briefing automático, error diagnostics, SLA tracking. Código: solo proto files. | `planning/.../E12:36` | 36–57 |
| 44 | MEDIUM | E12 resolution categories ausentes | Planning `E12:64-80` especifica 10 categorías (RESOLVED_E01, DEALER_OPTED_OUT, etc.). Código: no implementadas. | `planning/.../E12:64` | 64–80 |
| 45 | MEDIUM | E12 SLA ausente | Planning `E12:92-95`: "72h desde entrada hasta resolución + alerta >48h sin revisor". Código: cero tracking de SLA. | `planning/.../E12:92` | 92–95 |
| 46 | MEDIUM | TODO Sprint 3 sin cerrar | `discovery/internal/kg/confidence.go:6`: "Full formula (TODO Sprint 3): Bayesian combination with source independence". Sprint 3 ha terminado. El confidence scorer usa la fórmula simplificada indefinidamente. | `discovery/internal/kg/confidence.go:6` | 6 |
| 47 | MEDIUM | E13 VLM models no seleccionados | Planning `E13:69-75` especifica benchmark entre Phi-3.5, LLaVA, Qwen2-VL, InternVL2. No existe código de benchmark ni modelo seleccionado. | `planning/.../E13:69` | 69–75 |
| 48 | MEDIUM | E13 ONNX runtime ausente | Planning `E13` especifica ONNX INT8 para CPU-only inference. No existe dependency en ningún `go.mod`. | `planning/.../E13` vs `*/go.mod` | — |
| 49 | MEDIUM | E13 tiling ausente | Planning `E13:133-136` especifica batch inference con overlap de tiles para >50 vehículos en vitrina. No implementado. | `planning/.../E13:133` | 133–136 |
| 50 | MEDIUM | E13 prompt engineering ausente | Planning `E13:80-110` especifica multilingual prompt template + post-processing con JSON schema validation. No implementado. | `planning/.../E13:80` | 80–110 |
| 51 | MEDIUM | V20 LLM coherence ausente | Planning `V20_coherence_final_check.md` menciona LLM coherence check como sanity final. `v20_composite/` implementa composite scorer; verificar si LLM call está incluido. | `planning/.../V20:78` | 78–81 |
| 52 | MEDIUM | cardexUA duplicado en múltiples paquetes | `cardexUA` está definido localmente en `familia_a/be_kbo/kbo.go:56`, `familia_a/ch_zefix/zefix.go:56`, `familia_a/de_offeneregister/offeneregister.go:43`, `familia_a/es_borme/borme.go:47` y globalmente en `browser/config.go:80`. Riesgo de deriva si una instancia se actualiza y las otras no. | `discovery/internal/families/familia_a/*/` | varios |
| 53 | MEDIUM | E10 Sprint nota en producción | `e10_email/email.go:17`: "# Sprint 18 deliverable" — comentario de sprint en código de producción, debería ser issue/PR. | `extraction/internal/extractor/e10_email/email.go:17` | 17 |
| 54 | MEDIUM | E12 Sprint nota en producción | `e12_edge/edge.go:16`: "# gRPC server (Sprint 18 skeleton)" — ídem. | `extraction/internal/extractor/e12_edge/edge.go:16` | 16 |
| 55 | MEDIUM | E11 Sprint nota en producción | `e11_manual/manual.go:25`: "# Sprint 18 deliverable" — ídem. | `extraction/internal/extractor/e11_manual/manual.go:25` | 25 |
| 56 | MEDIUM | Planning Familia E vs código | Planning `E_dms_hosted.md` = DMS infrastructure detection (Familia E). Código `discovery/internal/families/familia_e/` tiene `dms_fingerprinter/`, `directory_mining/`, `ip_cluster/`. Estructura coherente pero `ip_cluster` no mencionado en planning Familia E. | `planning/03_DISCOVERY_SYSTEM/families/E_dms_hosted.md` vs `discovery/internal/families/familia_e/` | — |
| 57 | MEDIUM | robots.txt no centralizado | `browser/config.go:5`: "Respect for robots.txt (checked by caller before invoking this package)". No hay mecanismo que fuerce el check. Cada familia puede saltárselo sin detección. | `discovery/internal/browser/config.go:5` | 5 |
| 58 | MEDIUM | Métricas E10 no implementadas | Planning `E10_mobile_app_api.md` declara métricas `e10_app_found_rate`, `e10_apk_extracted_rate`. Código `e10_email/` no tiene estas métricas (ni puede, dado que implementa Email, no Mobile). | `planning/.../E10` vs `extraction/internal/metrics/` | — |
| 59 | MEDIUM | Métricas E13 no implementadas | Planning `E13` declara métricas `e13_screenshot_success_rate`, `e13_vlm_confidence_p50`. Cero código en `extraction/internal/metrics/` para E13. | `planning/.../E13` vs `extraction/internal/metrics/` | — |
| 60 | MEDIUM | INTERFACES.md E13 asunción | `INTERFACES.md:10`: "uniformidad de interfaz permite ... añadir estrategias E13+ sin refactorización." Correcto en diseño, pero E13 no está registrada en ningún pipeline/orchestrator, por lo que no sería automático. | `planning/.../INTERFACES.md:10` | 10 |
| 61 | MEDIUM | Stale planning dirs E11/E12 | `INTERFACES.md:30-31` muestra `e11_edge_onboarding/` y `e12_manual_review/`. Estos nombres nunca existieron en código. El planning nunca fue actualizado post-swap. | `INTERFACES.md:30` | 30–31 |
| 62 | MEDIUM | README "12 strategies" exacto pero incompleto | `README.md` dice "12 strategies" — numéricamente correcto (E01-E12), pero E10 no hace lo que el planning declara y E11/E12 están semánticamente intercambiadas. | `README.md:10` | 10 |
| 63 | MEDIUM | SPEC.md coherencia no verificada en detalle | `SPEC.md` requiere auditoría cruzada adicional con validators weights. Fuera de scope completo de esta pasada pero señalado para Track 2. | `SPEC.md` | — |
| 64 | MEDIUM | Planning `INTERFACES.md` nombra E11.Strategy = "EdgeOnboarding" | `INTERFACES.md:219`: `e11 := "E11"` en ejemplo de orquestador. La variable se llama `e11` pero el contexto dice "NextFallback apuntando a E11 o E12 según diagnóstico". Ambiguo tras el swap. | `INTERFACES.md:219` | 219 |
| 65 | MEDIUM | E11 EU Data Act compliance claim | Planning `E11:71` invoca EU Data Act compliance. Si E11 no está implementado, el compliance claim no tiene base en código. | `planning/.../E11:71` | 71 |
| 66 | MEDIUM | V05-V19 pesos composite inconsistentes | Planning V05-V19 declaran pesos individuales. Código `v20_composite/` debe agregarlos. Sin sincronización de nombres, los pesos pueden no coincidir con la spec. Requiere auditoría de `v20_composite/*.go`. | `planning/.../V20` vs `quality/internal/validator/v20_composite/` | — |
| 67 | MEDIUM | Familia O — rss subdirectorio | Código `discovery/internal/families/familia_o/rss/` existe. Planning `O_prensa_historicos.md` describe GDELT, NER, Wayback Monitor. RSS no mencionado explícitamente en planning familia O. | `planning/.../O_prensa_historicos.md` vs `familia_o/` | — |
| 68 | MEDIUM | Familia E — ip_cluster no en planning | Código `familia_e/ip_cluster/` existe. Planning `E_dms_hosted.md` no menciona IP clustering como subfamilia. | `planning/.../E_dms_hosted.md` vs `familia_e/ip_cluster/` | — |
| 69 | MEDIUM | Familia J — pappers no en planning | Código `familia_j/pappers/` existe. Planning `J_subjurisdicciones.md` no lo menciona explícitamente. | `planning/.../J_subjurisdicciones.md` vs `familia_j/pappers/` | — |
| 70 | MEDIUM | Familia G — mobilians no en planning | Código `familia_g/mobilians/` existe. Planning `G_asociaciones_sectoriales.md` — verificar si mencionado. | `planning/.../G_asociaciones_sectoriales.md` vs `familia_g/mobilians/` | — |
| 71 | LOW | Versión Go coherente | `README.md:16`: "Go 1.25+". Todos los `go.mod` (discovery/extraction/quality): `go 1.25.0`. ✓ Coherente. | `README.md:16` vs `*/go.mod` | — |
| 72 | LOW | Puertos coherentes entre docs | README: Caddy :443/:80, discovery :8080, extraction :8081, quality :8082, Prometheus :9090, Grafana :3001, Alertmanager :9093. Coincide con ARCHITECTURE.md. ✓ | `README.md` vs `ARCHITECTURE.md` | — |
| 73 | LOW | 15 familias coherentes | Planning: A-O = 15. Código: `familia_a`–`familia_o` = 15. README: "15 families". ✓ | `README.md` vs `planning/03*/families/` vs `discovery/internal/families/` | — |
| 74 | LOW | CardexBot UA correcto en discovery | `browser/config.go:80`: `cardexUA = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"`. Consistente en todas las familias auditadas. ✓ Policy R1 cumplida. | `discovery/internal/browser/config.go:80` | 80 |
| 75 | LOW | No stealth plugins | Config `browser/config.go:7-9` lista explícitamente como PROHIBIDOS: `playwright-stealth`, `undetected-chromedriver`, `puppeteer-extra`, TLS fingerprint spoofing (JA3/JA4), residential proxy evasion. Grep confirma cero usos. ✓ | `discovery/internal/browser/config.go:7` | 7–9 |
| 76 | LOW | Familia A — subregistros coherentes | Planning `A_registros_mercantiles.md` menciona BE (KBO), CH (Zefix), DE (Offene Register), ES (BORME), FR (SIRENE), NL (KVK). Código tiene exactamente esos 6 subdirectorios. ✓ | `planning/.../A_registros.md` vs `familia_a/` | — |
| 77 | LOW | Familia B — OSM + Wikidata | Planning `B_geocartografia.md`. Código: `familia_b/osm/` + `familia_b/wikidata/`. ✓ Coherente. | `planning/.../B_geocartografia.md` vs `familia_b/` | — |
| 78 | LOW | Familia C — crtsh + passive_dns + wayback | Planning `C_web_cartography.md`. Código: `familia_c/crtsh/`, `passive_dns/`, `wayback/`. ✓ | `planning/.../C_web_cartography.md` vs `familia_c/` | — |
| 79 | LOW | Familia F — 4 aggregators | Planning `F_aggregator_directories.md`: AutoCasion, AutoScout24, La Centrale, Mobile.de. Código: exactamente esos 4. ✓ | `planning/.../F_aggregator_directories.md` vs `familia_f/` | — |
| 80 | LOW | Familia H — 8 OEM networks | Código: bmw, ford, hyundai, mercedes, renault, stellantis, toyota, vwg + common = 9 subdirs. Verificar si planning H declara los mismos 8 OEMs. | `planning/.../H_redes_oem.md` vs `familia_h/` | — |
| 81 | LOW | Familia I — 7 inspection networks | Código: bosch_car_service, ct_be, dekra_de, dekra_fr, itv_es, mfk_ch, rdw_apk, tuv_de = 8 subdirs. Planning `I_redes_inspeccion.md`: verificar count. | `planning/.../I_redes_inspeccion.md` vs `familia_i/` | — |
| 82 | LOW | Familia K — searxng + marginalia | Planning `K_buscadores_alternativos.md`. Código: `searxng/` + `marginalia/`. ✓ | `planning/.../K_buscadores_alternativos.md` vs `familia_k/` | — |
| 83 | LOW | Familia L — googlemaps + linkedin + youtube | Planning `L_plataformas_sociales.md`. Código: `googlemaps/`, `linkedin/`, `youtube/`. ✓ | `planning/.../L_plataformas_sociales.md` vs `familia_l/` | — |
| 84 | LOW | Familia M — ch_uid + jobboards + vies | Planning `M_signals_fiscales.md`. Código: `ch_uid/`, `jobboards/`, `vies/`. ✓ | `planning/.../M_signals_fiscales.md` vs `familia_m/` | — |
| 85 | LOW | Familia N — censys + reverseip + shodan + subdomain | Planning `N_infra_intelligence.md`. Código: `censys/`, `reverseip/`, `shodan/`, `subdomain/`. ✓ | `planning/.../N_infra_intelligence.md` vs `familia_n/` | — |
| 86 | LOW | Familia O — gdelt + ner + wayback_monitor | Planning `O_prensa_historicos.md`. Código: `gdelt/`, `ner/`, `rss/`, `wayback_monitor/`. `rss/` no en planning (ver #67). | `planning/.../O_prensa_historicos.md` vs `familia_o/` | — |
| 87 | LOW | V01 coherente | Planning `V01_vin_checksum.md`: ISO 3779. Código: `v01_vin_checksum/`. ✓ | — | — |
| 88 | LOW | V02 coherente | Planning `V02_vin_decode_nhtsa.md`: vPIC NHTSA. Código: `v02_nhtsa_vpic/`. ✓ Nombre ligeramente distinto pero semánticamente correcto. | — | — |
| 89 | LOW | V03 coherente | Planning `V03_vin_decode_crosscheck.md`: DAT/EUR crosscheck. Código: `v03_dat_codes/`. ✓ Semánticamente correcto. | — | — |
| 90 | LOW | V04 coherente | Planning `V04_title_nlp_makemodel.md`. Código: `v04_nlp_makemodel/`. ✓ | — | — |
| 91 | LOW | V20 coherente | Planning `V20_coherence_final_check.md`. Código: `v20_composite/`. ✓ Nombre distinto pero rol correcto (composite final scorer). | — | — |
| 92 | LOW | E01-E04 prioridades correctas | Planning: E01=1200, E02=1100, E03=1000, E04=900. Código: idéntico. ✓ | `INTERFACES.md:242-246` vs `strategy.go:23-27` | — |
| 93 | LOW | Rate limiting implementado | `browser/config.go`: rate limiting (5s min interval per host, SQLite-persisted). README implica protección; código la cumple. ✓ | `discovery/internal/browser/config.go` | — |
| 94 | LOW | Tests en E01-E09 | Todos los paquetes e01–e09 tienen `*_test.go`. E10/E11/E12 también tienen tests. E13 no tiene tests (no existe). ✓ Para E01-E12. | `extraction/internal/extractor/*/` | — |
| 95 | LOW | Tests en V01-V20 | Todos los paquetes v01–v20 tienen `*_test.go`. ✓ | `quality/internal/validator/*/` | — |
| 96 | LOW | Tests en familias A-O | No auditado exhaustivamente en esta pasada. Recomendado para Track 2. | `discovery/internal/families/` | — |
| 97 | LOW | t.Skip no encontrado | Grep de `t.Skip` en todos los `*_test.go` retornó cero resultados. ✓ Sin tests silenciados. | `**/*_test.go` | — |
| 98 | LOW | CHANGELOG — no auditado vs git log | CHANGELOG vs `git log` requiere pasada manual completa. Señalado para Track 2. | `CHANGELOG.md` | — |
| 99 | LOW | deploy/observability — Grafana dashboards | `deploy/observability/` contiene config de Prometheus/Alertmanager. Verificar si JSON dashboards de Grafana existen y si las métricas declaradas en código tienen panel correspondiente. | `deploy/observability/` | — |
| 100 | LOW | internal/shared — contenido no auditado | `internal/shared/` existe. Contenido no auditado en esta pasada. Verificar si hay exported types sin importar. | `internal/shared/` | — |
| 101 | LOW | SQLite WAL claim | `README.md` menciona SQLite WAL mode. Verificar si la inicialización en código usa `PRAGMA journal_mode=WAL`. | `README.md` vs `discovery/internal/db/` | — |
| 102 | LOW | backup.sh age encryption | `README.md` menciona age-encrypted backups. Verificar si `deploy/scripts/backup.sh` usa age. | `deploy/scripts/backup.sh` | — |
| 103 | LOW | Familia D — plugins subdir en código, no en planning | Código `familia_d/plugins/` existe. Planning `D_cms_fingerprinting.md` puede no mencionarlo explícitamente. | `planning/.../D_cms_fingerprinting.md` vs `familia_d/plugins/` | — |
| 104 | LOW | Familia D — dms subdir redundante | Código tiene `familia_d/dms/` Y `familia_e/dms_fingerprinter/`. Posible solapamiento de responsabilidad entre familias D y E. | `familia_d/dms/` vs `familia_e/dms_fingerprinter/` | — |
| 105 | LOW | E08 PDF — dependencias externas | Planning `E08_pdf_catalog.md` menciona `pdfplumber`, `tesseract OCR`. Verificar si `extraction/go.mod` incluye esas dependencias Go equivalentes. | `planning/.../E08` vs `extraction/go.mod` | — |
| 106 | LOW | E09 Excel — parser Go | Planning `E09_csv_excel_feeds.md` menciona `pandas`, `openpyxl` (Python). Si el código es Go, verificar qué librería usa. | `planning/.../E09` vs `extraction/internal/extractor/e09_excel/` | — |
| 107 | LOW | E07 Playwright — módulo real | Planning `E07_playwright_xhr_discovery.md`: "Playwright XHR interception." Código `e07_playwright_xhr/`: verificar si usa `playwright-go` o stub. | `extraction/internal/extractor/e07_playwright_xhr/` | — |
| 108 | LOW | cardexUA duplicate risk | `cardexUA` definido en `familia_a/*/kbo.go:56`, `zefix.go:56`, `offeneregister.go:43`, `borme.go:47` además de `browser/config.go:80`. Si la URL del bot cambia, 4+ archivos deben actualizarse. Refactorizar a constante compartida en `internal/shared/`. | `discovery/internal/families/familia_a/*/` | varios |

---

## Conteo por severidad

| SEVERITY | COUNT |
|----------|-------|
| CRITICAL | 13 |
| HIGH | 23 |
| MEDIUM | 32 |
| LOW | 40 |
| **TOTAL** | **108** |

---

## Anexo A — Evidencia directa (greps y líneas citadas)

### A.1 Priority matrix — planning INTERFACES.md vs código strategy.go

```
PLANNING (planning/04_EXTRACTION_PIPELINE/INTERFACES.md:241-254):
PriorityE01 = 1200   PriorityE02 = 1100   PriorityE05 = 1050
PriorityE03 = 1000   PriorityE04 = 900    PriorityE06 = 800
PriorityE07 = 700    PriorityE09 = 400    PriorityE08 = 300
PriorityE10 = 200    PriorityE11 = 100    PriorityE12 = 0

CÓDIGO (extraction/internal/pipeline/strategy.go:22-33):
PriorityE12 = 1500   PriorityE01 = 1200   PriorityE02 = 1100
PriorityE03 = 1000   PriorityE05 = 950    PriorityE04 = 900
PriorityE06 = 850    PriorityE07 = 800    PriorityE08 = 700
PriorityE09 = 700    PriorityE10 = 600    PriorityE11 = 100

DELTA:
E05: planning=1050 → código=950 (-100)
E06: planning=800  → código=850 (+50)
E07: planning=700  → código=800 (+100)
E08: planning=300  → código=700 (+400)
E09: planning=400  → código=700 (+300)
E10: planning=200  → código=600 (+400) + estrategia diferente
E12: planning=0    → código=1500 (+1500) + nombre diferente
```

### A.2 E11/E12 swap — triple evidencia

```
planning/04_EXTRACTION_PIPELINE/INTERFACES.md:30-31:
│   ├── e11_edge_onboarding/
│   └── e12_manual_review/

planning/04_EXTRACTION_PIPELINE/INTERFACES.md:252-253:
PriorityE11 = 100  // Edge onboarding
PriorityE12 = 0    // Manual review

extraction/internal/extractor/ (dirs reales):
e11_manual/
e12_edge/

extraction/internal/pipeline/strategy.go:22:
PriorityE12 = 1500 // Edge push (Tauri client) — dealer-signed, highest trust
```

### A.3 RobotsChecker — ghost feature

```
README.md:75:
"robots.txt compliance — `RobotsChecker` is wired in all HTTP crawl paths."

ARCHITECTURE.md:172:
"`RobotsChecker` verifies robots.txt compliance before crawling any URL."

grep -rn "RobotsChecker" discovery/internal/ extraction/internal/
→ 0 results

discovery/internal/browser/browser.go:18:
"// robots.txt compliance is the caller's responsibility."

discovery/internal/browser/config.go:5:
"//  2. Respect for robots.txt (checked by caller before invoking this package)."
```

### A.4 E10 skeleton confirmation

```
extraction/internal/extractor/e10_email/email.go:
line  3: // # Architecture (Sprint 18 skeleton)
line 17: // # Sprint 18 deliverable
line 19: // This sprint delivers the skeleton: interface definition, Applicable logic,
line 20: // and an Extract stub that signals "awaiting attachment" when no staging rows
line 21: // are present. The real IMAP poller and staging table wiring are Phase 4 work.
line 41: // from the staging table. Implement with a real DB-backed reader in Phase 4.
line 66: // table is available (Phase 4).
```

### A.5 E12 noOpStore

```
extraction/internal/extractor/e12_edge/edge.go:
line 16: // # gRPC server (Sprint 18 skeleton)
line 22: // middleware) is Phase 4 work. This sprint delivers:
line 25: //   - A no-op store implementation for use in main.go until Phase 4 wires
line 62: // noOpStore is the default store used until the gRPC server is wired (Phase 4)
```

### A.6 TODO Sprint 3 stale

```
discovery/internal/kg/confidence.go:6:
"// Full formula (TODO Sprint 3): Bayesian combination with source independence"
```

### A.7 CONTRIBUTING wrong path

```
CONTRIBUTING.md:22:
"Follow the same pattern as families but in `extraction/internal/strategy/e{NN}_{name}/`."

Actual directory: extraction/internal/extractor/e{NN}_{name}/
```

### A.8 V05-V19 naming matrix (planning dir → código dir)

```
V05 image_classification_ml   → v05_image_quality
V06 identity_convergence      → v06_photo_count
V07 image_quality             → v07_price_sanity
V08 image_phash_dedup         → v08_mileage_sanity
V09 watermark_logo_detection  → v09_year_consistency
V10 vehicle_binary_classifier → v10_source_url_liveness
V11 mileage_sanity            → v11_nlg_quality
V12 year_registration_consistency → v12_cross_source_dedup
V13 price_outlier_detection   → v13_completeness
V14 vat_mode_detection        → v14_freshness
V15 currency_normalization    → v15_dealer_trust
V16 cross_source_convergence  → v16_photo_phash
V17 geolocation_validation    → v17_sold_status
V18 equipment_normalization   → v18_language_consistency
V19 nlg_description_generation → v19_currency
```

### A.9 Policy R1 — resultado limpio

```
grep -rn "stealth|playwright-extra|puppeteer-extra|curl_cffi|tls_client|undetected|residential proxy"
→ CERO hits en código fuente

discovery/internal/browser/config.go:7-9 (prohibición explícita):
//  4. NO stealth plugins (playwright-stealth, undetected-chromedriver, puppeteer-extra).
//  5. NO TLS fingerprint spoofing (JA3/JA4).
//  6. NO residential proxy evasion.

browser/config.go:80: cardexUA = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
→ Consistente en todas las familias auditadas.
```

---

## Recomendaciones prioritarias

1. **RobotsChecker (CRITICAL):** Implementar un `RobotsChecker` centralizado en `discovery/internal/browser/` o eliminar el claim de README y ARCHITECTURE. El riesgo actual es crawl sin robots.txt check si un caller omite la validación.

2. **E11↔E12 swap (CRITICAL):** Decidir la fuente de verdad: ¿planning o código? Sincronizar `INTERFACES.md`, `CONTRIBUTING.md`, `ARCHITECTURE.md` y los comentarios de código en una sola sesión.

3. **Priority matrix (CRITICAL/HIGH):** Actualizar `extraction/internal/pipeline/strategy.go` para que las prioridades coincidan con `INTERFACES.md`, o actualizar `INTERFACES.md` para reflejar la lógica de negocio actual.

4. **V05-V19 naming (CRITICAL/HIGH):** Crear un documento de mapping canónico que explique por qué los números de planning y código divergen, o renombrar los directorios para que coincidan.

5. **CONTRIBUTING path (CRITICAL):** Corregir `CONTRIBUTING.md:22` de `strategy/` a `extractor/`.

6. **TODO Sprint 3 (MEDIUM):** Convertir en GitHub issue o implementar la fórmula Bayesiana en `confidence.go`.

7. **cardexUA duplicación (LOW):** Mover `cardexUA` a `internal/shared/` y hacer que todas las familias importen desde ahí.
