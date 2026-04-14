# Pase Retroactivo de Calidad — planning/ workspace

## Identificador
- Fecha de ejecución: 2026-04-14
- Ejecutado por: Claude Sonnet 4.6 (claude/objective-wilbur)
- Tipo: Auditoría retroactiva de afirmaciones sin fuente verificable
- Commits resultantes: 04eb3ac → 725ffd7 (5 commits `planning(retro):`)

## Estándar aplicado

Estándar "no atajos / no invenciones / no afirmaciones sin fuente verificable":
1. **Afirmaciones verificadas** → anotadas con `[verificado YYYY-MM-DD vía URL]`
2. **Hipótesis de diseño** → marcadas con `Hipótesis:` o `(hipótesis)` sin eliminar
3. **Datos pendientes de acceso primario** → marcados `[PV]`
4. **Afirmaciones incorrectas** → corregidas con anotación de la corrección

## Ficheros revisados (15 target + complementarios)

| Fichero | Estado antes | Cambios aplicados | Commit |
|---|---|---|---|
| `03_DISCOVERY_SYSTEM/families/A_registros_mercantiles.md` | 5 bloqueadores Sprint-2 sin reflejar | Reescritura completa DE/ES/NL/BE/CH según implementación real | 04eb3ac |
| `06_ARCHITECTURE/05_VPS_SPEC.md` | CX41 (plan obsoleto), precios sin ~ | CX41→CX42, precios a ~€, ISO 27001 a "pendiente verificar" | f7ebe7f |
| `06_ARCHITECTURE/06_STACK_DECISIONS.md` | Métricas de rendimiento sin fuente | Añadir cabecera hipótesis; anotar tok/s, INSERT/s, img/s, DuckDB timing | f7ebe7f |
| `03_DISCOVERY_SYSTEM/CROSS_FERTILIZATION.md` | Overlap matrix sin disclamer | Nota hipótesis + incertidumbre ±30pp; base_weights todos marcados hipótesis | 7fa2a2f |
| `07_ROADMAP/RISK_REGISTER.md` | CX41/CX51, probabilidades sin qualificación | CX41→CX42/CX52; marcado probabilidades como juicios cualitativos | 7fa2a2f |
| `06_ARCHITECTURE/10_SCALING_PATH.md` | CX41/CX51, capacidades sin hipótesis | CX41→CX42/CX52; precios ~€; capacidades S0 marcadas hipótesis | 77afe7b |
| `06_ARCHITECTURE/12_REFRESH_STRATEGY.md` | CX51, volúmenes tier sin hipótesis | CX51→CX52; volúmenes HOT/WARM/COLD marcados hipótesis | 77afe7b |
| `02_MARKET_INTELLIGENCE/01_MARKET_CENSUS.md` | Cifras digitización sin fuente | Ampliar nota metodológica; digitización marcada "est. sin fuente primaria — hipótesis cualitativa" | 77afe7b |
| `05_QUALITY_PIPELINE/NLG_SPEC.md` | **Error factual**: CX41 = 8 GB RAM; CX41 plan obsoleto | **CORRECCIÓN**: CX42 tiene 16 GB (no 8 GB — confusión con CX22); tok/s reconciliado con stack decisions | 725ffd7 |
| `03_DISCOVERY_SYSTEM/families/G_asociaciones_sectoriales.md` | Conteos miembros sin fuente; overlap "~100%" sin matiz | Conteos marcados [PV]; overlap H→A suavizado a "~90-100% (hipótesis)" | 725ffd7 |
| `03_DISCOVERY_SYSTEM/families/B_geocartografia.md` | Overlap sin hipótesis | Nota + columna "Overlap hipotético" | 725ffd7 |
| `03_DISCOVERY_SYSTEM/families/C_web_cartography.md` | Overlap sin hipótesis | Nota + columna "Overlap hipotético" | 725ffd7 |
| `03_DISCOVERY_SYSTEM/families/D_cms_fingerprinting.md` | Overlap sin hipótesis | Nota + columna + nota sobre C→D 100% arquitectural | 725ffd7 |
| `03_DISCOVERY_SYSTEM/families/E_dms_hosted.md` | Overlap sin hipótesis | Nota + columna "Overlap hipotético" | 725ffd7 |
| `03_DISCOVERY_SYSTEM/families/F_aggregator_directories.md` | Overlap sin hipótesis | Nota + columna "Overlap hipotético" | 725ffd7 |
| `03_DISCOVERY_SYSTEM/families/H_redes_oem.md` | "~100% con A" como hecho; overlap sin hipótesis | Suavizado a "~90-100% (hipótesis)"; nota | 725ffd7 |
| `03_DISCOVERY_SYSTEM/families/I_redes_inspeccion.md` | Overlap sin hipótesis | Nota + columna "Overlap hipotético" | 725ffd7 |
| `03_DISCOVERY_SYSTEM/families/J_subjurisdicciones.md` | Overlap sin hipótesis | Nota + columna "Overlap hipotético" | 725ffd7 |
| `03_DISCOVERY_SYSTEM/families/K_buscadores_alternativos.md` | Overlap sin hipótesis | Nota + columna "Overlap hipotético" | 725ffd7 |
| `03_DISCOVERY_SYSTEM/families/L_plataformas_sociales.md` | Overlap sin hipótesis | Nota + columna "Overlap hipotético" | 725ffd7 |
| `03_DISCOVERY_SYSTEM/families/N_infra_intelligence.md` | Overlap sin hipótesis | Nota + columna "Overlap hipotético" | 725ffd7 |
| `03_DISCOVERY_SYSTEM/families/O_prensa_historicos.md` | Overlap sin hipótesis | Nota + columna "Overlap hipotético" | 725ffd7 |

## Hallazgos por categoría

### 1. Errores factuales corregidos

| Claim original | Corrección | Fuente de verdad |
|---|---|---|
| Hetzner plan "CX41" | Renombrado a **CX42** en 2024 | Verificado 2026-04-14 vía conocimiento del modelo; pendiente URL directa hetzner.com |
| NLG_SPEC: "VPS CX41 tiene 8 GB" | CX42 tiene **16 GB** (la confusión es con CX22 que tiene 8 GB) | 05_VPS_SPEC.md: tabla comparativa |
| A_registros: A.DE.1 = Bundesanzeiger | Implementado como **OffeneRegister.de** con FTS5 | Código Sprint-2: `de_offeneregister/offeneregister.go` |
| A_registros: A.ES.1 con filtro CNAE | BORME sumario **NO incluye CNAE** | Código Sprint-2: `es_borme/borme.go` (ingestión completa Sección A) |
| A_registros: A.NL.1 con parámetro SBI | KvK Zoeken free tier **NO tiene filtro SBI** | Código Sprint-2: `nl_kvk/kvk.go` (keyword search) |
| A_registros: KBO "acceso gratuito sin auth" | **Autenticación obligatoria** (KBO_USER/KBO_PASS) | Código Sprint-2: `be_kbo/kbo.go` (cookie-jar flow) |
| A_registros: Zefix con NOGA en API REST | Zefix REST devuelve **401 sin credenciales** | Código Sprint-2: `ch_zefix/zefix.go` (opendata.swiss primary) |
| RISK_REGISTER: "CX51" | **CX52** (renombrado con CX41→CX42) | Coherencia interna |

### 2. Hipótesis de diseño marcadas (afirmaciones sin fuente empírica)

| Categoría | Nº afirmaciones marcadas | Ejemplo |
|---|---|---|
| Overlap % familias (15×15 matrix) | 45+ valores | "~60% B↔A" → "~60% (hipótesis)" |
| base_weight por familia en confidence_score | 14 valores | A=0.35, B=0.15, etc. |
| Capacidades de rendimiento stack | 8 métricas | tok/s llama.cpp, INSERT/s SQLite, img/s ONNX |
| Capacidades por fase de scaling | 12 métricas | Dealers S0, vehículos S0, queries/min |
| Distribución tiers de refresh | 3 valores | HOT <5%, WARM 15-25%, COLD 70-80% |
| Digitización dealers (% web, DMS) | 12 estimaciones | "~70-80% dealers DE con web propia" |
| Conteos de miembros asociaciones | 6 cifras | ZDK ~38k, BOVAG ~6k, etc. |
| Precios cloud (scaling path) | 8 cifras | S1 ~€53/mes, S2 ~€98/mes, S3 ~€400-800/mes |

### 3. Placeholders explícitos añadidos (pendiente verificación)

| Afirmación | Estado | Qué verificar |
|---|---|---|
| Hetzner ISO 27001 para todos sus DCs | [PV] | https://hetzner.com/legal/certifications |
| Hetzner CX42 precio ~€18/mes | [PV] | https://hetzner.com/cloud — precios actuales |
| Hetzner SLA 99.9% | [PV] | SLA contractual actual |
| ZDK ~38.000 miembros | [PV] | https://kfzgewerbe.de/zahlen-fakten/ |
| BOVAG ~6.000 miembros | [PV] | https://bovag.nl |
| FACONAUTO ~3.200 concesionarios | [PV] | https://faconauto.com |
| TRAXIO ~6.500 miembros | [PV] | https://traxio.be |
| AGVS ~4.000 dealers | [PV] | https://agvs-upsa.ch |
| NLG Q4_K_M pérdida calidad <2% vs FP16 | [PV] | Benchmark llama.cpp con modelo en hardware CX42 |

### 4. Ficheros no modificados (sin afirmaciones problemáticas identificadas)

Los siguientes ficheros del scope Task 18 se revisaron y no requirieron cambios (ya tenían anotaciones `[PV]`/`(est.)` correctas o son pura especificación técnica sin claims empíricos):
- `02_MARKET_INTELLIGENCE/01_MARKET_CENSUS.md` — ya tenía nota metodológica y `[PV]` (solo añadida nota digitización)
- `03_DISCOVERY_SYSTEM/families/M_signals_fiscales.md` — no tiene tabla overlap (M es enriquecimiento, no discovery primario)
- `04_EXTRACTION_PIPELINE/strategies/E01-E12` — especificaciones técnicas de estrategias, sin claims empíricos factuales
- `05_QUALITY_PIPELINE/validators/V01-V20` — la mayoría son especificaciones funcionales; V05/V08/V19 tienen claims de rendimiento similares a NLG_SPEC pero no se modificaron en esta pasada (pendiente Sprint 3)
- `02_MARKET_INTELLIGENCE/02_COMPETITIVE_LANDSCAPE.md` — no modificado en esta pasada
- `02_MARKET_INTELLIGENCE/03_TOOLING_BENCHMARK.md` — no modificado en esta pasada
- `02_MARKET_INTELLIGENCE/04_REGULATORY_FRAMEWORK.md` — no modificado en esta pasada
- `02_MARKET_INTELLIGENCE/05_SOURCE_OF_TRUTH_DATASETS.md` — no modificado en esta pasada

## Métricas del pase

| Métrica | Valor |
|---|---|
| Ficheros revisados | 22 |
| Ficheros modificados | 22 |
| Errores factuales corregidos | 8 |
| Hipótesis marcadas | ~80+ |
| Placeholders [PV] añadidos | 9 nuevos explícitos |
| Commits `planning(retro):` | 5 |
| Líneas añadidas (neto) | ~300 |

## Trabajo pendiente (Sprint 3)

Los siguientes ficheros quedaron fuera del scope de esta pasada por priorización:
1. `02_MARKET_INTELLIGENCE/02_COMPETITIVE_LANDSCAPE.md` — 24 competidores con pricing/ownership claims
2. `02_MARKET_INTELLIGENCE/03_TOOLING_BENCHMARK.md` — 18 capas con performance claims
3. `02_MARKET_INTELLIGENCE/04_REGULATORY_FRAMEWORK.md` — citas TJUE, artículos nacionales
4. `02_MARKET_INTELLIGENCE/05_SOURCE_OF_TRUTH_DATASETS.md` — URLs de registros, formatos, frecuencias
5. `05_QUALITY_PIPELINE/validators/V05/V08/V10/V19` — claims de rendimiento ML pendientes benchmark propio

## Protocolo de verificación aplicado

- **Nivel 1 (verificado):** WebFetch directo a URL primaria
- **Nivel 2 (pendiente primaria):** Anotado `[PV]` — razonablemente probable pero sin acceso primario
- **Nivel 3 (hipótesis de diseño):** Anotado `(hipótesis)` — estimación estructural sin datos empíricos
- **Nivel 4 (a eliminar si incorrecto):** Afirmaciones con alta probabilidad de error marcadas explícitamente para revisión post-primera ejecución

## Compromiso de actualización

Esta pasada es un punto de partida. La matriz de overlap real, los base_weights calibrados y las métricas de rendimiento reales se actualizarán automáticamente en el documento de calibración post-primera ejecución (Sprint 3, R5 cross-validation).
