# E07 — XHR/AJAX endpoint discovery vía Playwright transparente

## Identificador
- ID: E07, Nombre: XHR/AJAX endpoint discovery via Playwright, Categoría: Dynamic-rendering
- Prioridad: 700
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Los sites dealer modernos construidos con React, Vue, Angular, o frameworks similares cargan su inventario via XHR/AJAX calls a un endpoint JSON backend. El HTML inicial no contiene datos: solo un shell vacío y bundles JS. E07 usa Playwright con UA CardexBot identificable para navegar al inventory page, intercepta las network requests que el frontend hace, identifica el endpoint JSON de inventario, y usa ese endpoint directamente en adelante (sin necesidad de Playwright en ciclos futuros).

**Distinción crítica:** E07 NO evade controles de acceso. No usa playwright-stealth, no randomiza UA, no simula comportamiento humano, no usa proxies. Es Playwright en modo completamente transparente, identificable. Si el site detecta el bot y devuelve datos vacíos o bloquea → E07 registra el fallo y escala a E11. E07 no bypassa.

## Target de dealers
- Sites React/Vue/Next.js/Nuxt con inventory cargado via XHR
- Sites con DMS frontend custom que consumen una API propia
- Sites Wordpress con plugins de inventario que usan AJAX
- Dealers con plataformas modernas donde E01-E06 no encuentran datos en HTML estático
- Estimado: 40-55% del universo dealer con site moderno

## Sub-técnicas

### E07.1 — Lanzamiento de sesión Playwright transparente

```
User-Agent: CardexBot/1.0 (+https://cardex.io/bot)
(No modificación de ningún otro header de browser fingerprint)
(No playwright-stealth, no evasión)
(No viewport spoofing)
```

Playwright lanza Chromium estándar con el UA sobreescrito a CardexBot. El site puede detectar el bot via:
- UA no-browser: expected, CardexBot no intenta parecerse a un browser
- Automation flags (`navigator.webdriver=true`): no se ocultan
- Headless detection: no se oculta

Si el site bloquea por cualquiera de estas razones → `STRATEGY_FAILED_PERMANENT`, escalar a E11.

### E07.2 — Navegación al inventory page + network interception

1. Iniciar network request interceptor (todos los XHR/fetch calls)
2. Navegar a la inventory page del dealer (discovery via sitemap o slug patterns conocidos)
3. Esperar a que se complete la carga del inventario (criterio: network idle 2s, o selector CSS de inventory item visible)
4. Recopilar todas las requests XHR interceptadas

### E07.3 — Identificación del endpoint JSON de inventario

Filtros sobre las requests interceptadas:
- `Content-Type: application/json` en response
- URL contiene keywords: `/inventory`, `/vehicles`, `/cars`, `/stock`, `/listings`, `/vehicules`, `/fahrzeuge`, `/coches`, `/autos`
- Response body es un array o objeto con >N items que contienen campos vehicle-like (Make/Model/Year/Price)

Si múltiples candidatos → seleccionar el de mayor cardinalidad (más vehículos en la response).

### E07.4 — Extracción directa del endpoint identificado

Una vez identificado el endpoint:
1. Registrarlo en `dealer_web_presence.rss_feed_url` (o campo `api_endpoint`) para ciclos futuros
2. Hacer request directa al endpoint (sin Playwright) con paginación si aplica
3. En ciclos futuros, usar E02-style direct API call sin necesidad de re-ejecutar Playwright

E07 "aprende" el endpoint y convierte al dealer en E02-like para ciclos posteriores. El coste alto de Playwright es solo del primer ciclo.

### E07.5 — Extracción de token de autenticación si presente

Si el frontend incluye un token en los headers de sus XHR calls (Bearer, API key, CSRF token):
- E07 captura el token de los request headers interceptados
- Si el token parece de larga duración (no session-bound) → guardar para uso directo
- Si el token es session-bound (CSRF) → E07 debe ejecutarse con Playwright en cada ciclo (coste mantenido)
- Token guardado con cifrado en secrets store, NUNCA en plaintext en DB

### E07.6 — Scroll paginado para SPA con lazy loading

Algunos frontends usan scroll infinito en lugar de paginación explícita. E07 puede:
1. Scroll automático hacia el fondo de página
2. Capturar cada batch de XHR requests generado por el scroll
3. Agregar todos los vehículos descargados en los batches

Limitación: scroll hasta detectar "no new requests" o hasta N max scrolls (configurable, default 20).

## Formato de datos esperado
JSON retornado por el endpoint XHR identificado. El formato es propietario del frontend del dealer. La normalización aplica el mismo YAML-driven field mapper que E05 + heurísticas de campo nombre.

## Campos extraíbles típicamente
Dependiendo del backend que alimenta el frontend:
- Con DMS backend: todos los campos críticos + secundarios
- Con CMS plugin backend: Make, Model, Year, Price, SourceURL, ImageURLs
- Con custom backend: variable — el field mapper generalista captura lo que puede

## Base legal
- Playwright con UA identificable: acceso equivalente a cualquier cliente HTTP con identificación
- No evasión: el site puede detectar y bloquear → se acepta el bloqueo sin evasión
- Interceptación de network: es inspección del tráfico propio del proceso Playwright, no MITM
- Base: `public_web_access` con UA identificable
- robots.txt: consultado antes de navegar — si inventory path en `Disallow`, E07 no navega

## Métricas de éxito
- `e07_endpoint_discovered_rate` — % executions donde se identifica endpoint JSON
- `e07_block_rate` — % executions donde el site bloquea CardexBot (señal de E11 necesario)
- `e07_endpoint_stability` — % endpoints descubiertos en ciclo anterior que siguen válidos
- `e07_vs_playwright_cycles` — % dealers donde tras primer ciclo Playwright, el endpoint se usa directo

## Implementación
- Módulo Go: `services/pipeline/extraction/strategies/e07_playwright_xhr/`
- Dependencias: `github.com/playwright-community/playwright-go`
- **PROHIBIDO:** playwright-stealth, playwright-extra, cualquier plugin de evasión
- Sub-módulo: `session_manager.go` — pool de Playwright instances, UA setup, lifecycle
- Sub-módulo: `network_interceptor.go` — captura y análisis de XHR requests
- Sub-módulo: `endpoint_classifier.go` — identificación del endpoint de inventario
- Sub-módulo: `scroll_paginator.go` — lazy loading via scroll automático
- Sub-módulo: `endpoint_registry.go` — persistencia de endpoints descubiertos para re-uso
- Coste cómputo: alto (Chromium headless ~300MB RAM por instancia, CPU moderado)
- Instancias concurrentes: limitadas por RAM disponible (max 3 en VPS CX41)
- Cron: primer ciclo Playwright; ciclos posteriores via endpoint directo (E02-style)

## Fallback strategy
Si E07 falla:
- Si fallo por bloqueo explícito (403, empty data, anti-bot detected): escalar a E11 (Edge onboarding)
- Si fallo por timeout o rendering error: reintentar 1 vez con mayor wait time; si persiste → E11
- NUNCA escalar a técnicas de evasión

## Riesgos y mitigaciones
- R-E07-1: site bloquea CardexBot UA. Mitigación: registrar bloqueo, escalar a E11. No evadir.
- R-E07-2: endpoint XHR requiere auth session-bound imposible de mantener. Mitigación: ejecutar Playwright en cada ciclo (costoso); si inviable, escalar a E11.
- R-E07-3: SPA con múltiples endpoints (uno por marca, por estado, etc.). Mitigación: capturar todos los endpoints relevantes y hacer requests directas a todos; agregar resultados.
- R-E07-4: Playwright consume demasiados recursos para el VPS. Mitigación: queue serializado de E07 jobs, max 3 concurrentes, priorización por dealer importance.
- R-E07-5: site cambia su endpoint entre ciclos. Mitigación: health check semanal del endpoint guardado; si 404, re-ejecutar discovery Playwright.

## Iteración futura
- E07 como extractor de aprendizaje: los endpoints descubiertos alimentan el registry de E05 (nuevos DMS providers identificados)
- WebSocket interception: algunos DMS modernos usan WebSocket para inventario real-time
- Soporte de service workers: algunos PWA dealer usan SW para cache del inventario — inspección del SW cache
