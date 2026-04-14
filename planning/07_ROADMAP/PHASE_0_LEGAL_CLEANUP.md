# PHASE_0 — Legal Cleanup

## Identificador
- ID: P0, Nombre: Legal Cleanup — Purga de código ilegal legacy
- Estado: PENDING
- Dependencias de fases previas: ninguna (fase inicial, puede arrancar inmediatamente)
- Fecha de documentación: 2026-04-14

## Propósito y rationale

El repositorio contiene código heredado que implementa técnicas de evasión activa de detección de bots: `stealth_http.py`, `stealth_browser.py`, `StealthEngine` en `api_crawler/main.go`, el User-Agent `Googlebot` en `sitemap_vacuum`, `proxy_manager.py`, y librerías como `curl_cffi` y `playwright-stealth`. Este código no puede coexistir con el modelo legal de CARDEX descrito en `ILLEGAL_CODE_PURGE_PLAN.md`.

El objetivo de P0 es llevar el repositorio al estado de "cero técnicas de evasión" antes de construir nada más encima. Construir sobre código ilegal significa que cualquier cosa producida después hereda la contaminación. P0 no es limpieza cosmética — es la base del edificio.

## Objetivos concretos

1. Desactivar y eliminar `stealth_http.py` y `stealth_browser.py` completamente
2. Eliminar el campo `StealthEngine` y toda la lógica stealth de `api_crawler/main.go`
3. Reemplazar el User-Agent `Googlebot` de `sitemap_vacuum` por `CardexBot/1.0`
4. Eliminar `proxy_manager.py` (rotación de proxies residenciales)
5. Limpiar `base_scraper.py` de imports y llamadas a librerías blacklist
6. Purgar `curl_cffi`, `playwright-stealth` y cualquier otra dependencia de la blacklist de `go.mod`, `requirements.txt`, `package.json`
7. Activar el CI illegal-pattern linter como gate bloqueante en Forgejo
8. Marcar cada entrada de `ILLEGAL_CODE_PURGE_PLAN.md` como `PURGED` con fecha y hash de commit de la purga
9. Verificar que el robot de crawling usa exclusivamente `CardexBot/1.0` en todas las rutas de código

## Entregables

| Entregable | Descripción | Verificación |
|---|---|---|
| Código limpio en `main` | Sin imports ni llamadas a módulos de la blacklist | `grep` criterion CS-0-1 |
| `go.mod` / `requirements.txt` limpios | Sin dependencias blacklist | `grep` criterion CS-0-2 |
| CI illegal-pattern linter activo | `.forgejo/workflows/ci.yml` con step `illegal-pattern-scan` | PR test E2E |
| `ILLEGAL_CODE_PURGE_PLAN.md` completado | Cada entrada marcada PURGED + fecha + commit | Revisión manual |
| CardexBot UA en todas las rutas | 100% HTTP requests con UA correcto | criterion CS-0-3 |
| Tests de regresión de crawlers | Tests que verifican UA correcto en cada módulo | CI green |

## Criterios cuantitativos de salida

### CS-0-1: Cero ocurrencias de patrones ilegales en fuentes

```bash
# Debe retornar 0 líneas
grep -rEn \
  "(curl_cffi|playwright.*stealth|stealth.*playwright|2captcha|scrapingbee|\
  impersonate.*chrome|JA3Fingerprint|JA4Fingerprint|residential.*proxy|\
  rotating.*proxy|fakeUserAgent|Googlebot|bot\.googlebot)" \
  --include="*.go" --include="*.py" --include="*.ts" --include="*.rs" \
  --include="*.js" \
  . | grep -v "_test\." | grep -v "ILLEGAL_CODE_PURGE_PLAN"
# Resultado esperado: (vacío — 0 matches)
```

### CS-0-2: Cero dependencias blacklist en manifiestos

```bash
# go.mod
grep -E "(utls|CycleTLS|tls-client.*bogdanfinn|curl.cffi|playwright.stealth)" go.mod
# Resultado esperado: (vacío)

# requirements.txt (y requirements-*.txt)
grep -E "(curl.cffi|playwright.stealth|2captcha|anticaptcha|capsolver)" requirements*.txt 2>/dev/null
# Resultado esperado: (vacío)
```

### CS-0-3: 100% de módulos HTTP con CardexBot/1.0 UA

```bash
# Todos los módulos que crean http.Client o playwright.Browser deben tener CardexBot UA
# Este check verifica que el UA está presente en cada archivo que use net/http directamente
FILES_WITH_HTTP=$(grep -rl "net/http\|playwright\|chromedp" --include="*.go" --include="*.py" .)
FILES_WITH_BOT_UA=$(grep -rl "CardexBot" --include="*.go" --include="*.py" .)
# La diferencia debe ser 0 (o los archivos sin CardexBot deben ser solo tipos helpers sin peticiones directas)
```

### CS-0-4: CI linter rechaza reintroducción (test E2E del linter)

```bash
# Test: crear un archivo temporal con patrón ilegal y verificar que CI falla
echo 'import curl_cffi' > /tmp/test_illegal.py
# Ejecutar solo el step de scan sobre este archivo
# Resultado esperado: exit code 1
```

### CS-0-5: ILLEGAL_CODE_PURGE_PLAN.md completo

```bash
# Ninguna entrada en estado != PURGED
grep -c "^| \(TODO\|IN_PROGRESS\)" planning/ILLEGAL_CODE_PURGE_PLAN.md
# Resultado esperado: 0
```

## Métricas de progreso intra-fase

| Métrica | Descripción | Objetivo |
|---|---|---|
| `purge_entries_total` | Total de entradas en ILLEGAL_CODE_PURGE_PLAN.md | — (fijo) |
| `purge_entries_done` | Entradas marcadas PURGED | = purge_entries_total |
| `illegal_pattern_matches` | Output de CS-0-1 en el estado actual | Decrece a 0 |
| `blacklist_deps_count` | Dependencias blacklist en go.mod + requirements.txt | Decrece a 0 |
| `modules_with_correct_ua` | Módulos HTTP con CardexBot/1.0 | Aumenta a 100% |

## Actividades principales (orden recomendado)

1. **Auditoría completa del código actual** — ejecutar CS-0-1 y CS-0-2 para obtener inventario completo de lo que existe; actualizar ILLEGAL_CODE_PURGE_PLAN.md si hay entradas no documentadas
2. **Eliminar archivos completos** — `stealth_http.py`, `stealth_browser.py`, `proxy_manager.py` son candidatos a eliminación total (no refactoring)
3. **Refactorizar `base_scraper.py`** — eliminar imports de librerías blacklist; sustituir por `requests` + `CardexBot/1.0` UA puro
4. **Refactorizar `api_crawler/main.go`** — eliminar `StealthEngine` field y todo el código stealth; implementar `net/http` puro con `CardexBot/1.0`
5. **Corregir `sitemap_vacuum`** — sustituir `Googlebot` UA por `CardexBot/1.0`
6. **Limpiar manifiestos** — `go mod tidy`, `pip-compile --upgrade` con blacklist excluida
7. **Activar CI linter** — añadir step `illegal-pattern-scan` a `.forgejo/workflows/ci.yml` y verificar que rechaza la PR de limpieza si hay residuos
8. **Escribir tests de regresión** — cada módulo HTTP refactorizado debe tener un test que verifique el UA
9. **Actualizar ILLEGAL_CODE_PURGE_PLAN.md** — marcar cada entrada como PURGED con fecha + commit hash
10. **Retrospectiva** — ejecutar todos los criterios CS-0-* y documentar resultados

## Dependencias externas

- Acceso de escritura al repositorio (presente)
- Comprensión del código legacy (requiere lectura de cada archivo afectado antes de modificar)
- No hay dependencias de otros sistemas externos

## Riesgos específicos de la fase

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Código stealth usado implícitamente por código legítimo | MEDIA | ALTA | Leer dependencias completas del módulo antes de eliminar; tests de regresión de funcionalidad |
| Refactoring de `base_scraper.py` introduce regresiones en extractores | MEDIA | MEDIA | Tests de integración sobre dataset de muestra antes y después del refactor |
| Dependencia transitiva que incluye librería blacklist sin ser directa | BAJA | ALTA | `go mod graph | grep <blacklisted>` y `pip show <pkg> | grep Requires` para dependencias transitivas |
| CI linter tiene falsos positivos en comentarios de código | BAJA | BAJA | Añadir `# noqa` pattern exceptions solo en líneas de comentario documentado |

## Retrospectiva esperada (plantilla)

Al cerrar P0, evaluar:
- ¿Cuántos archivos tuvieron que ser refactorizados vs. eliminados?
- ¿El refactoring de `base_scraper.py` preservó toda la funcionalidad de extracción?
- ¿El CI linter tardó en activarse por algún problema de configuración?
- ¿Hubo dependencias transitivas no anticipadas en la auditoría inicial?
- ¿Los tests de regresión cubrieron todos los módulos afectados?
