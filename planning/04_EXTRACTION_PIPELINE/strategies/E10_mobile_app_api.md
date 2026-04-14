# E10 — Mobile app API endpoints

## Identificador
- ID: E10, Nombre: Mobile app API endpoints, Categoría: Mobile-API
- Prioridad: 200
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Algunos grupos dealer de mediano y gran tamaño han desarrollado aplicaciones móviles propias (iOS App Store, Google Play) para que sus compradores naveguen el inventario. Estas apps consumen APIs JSON backend que, por su naturaleza, exponen el inventario en formato estructurado completo. La identificación de estos endpoints via APK analysis (legal sobre APKs públicos de Play Store) o via documentación técnica pública permite un acceso directo sin necesidad de Playwright.

E10 es de prioridad baja (200) porque cubre menos del 2% del universo dealer y el esfuerzo de análisis es alto. Se aplica solo a grupos dealer grandes con app propia identificable.

## Target de dealers
- Grupos dealer grandes con app propia en Google Play / App Store
- Dealers con plataformas DMS que tienen companion app documentada
- Cadenas multinacionales (ej. un grupo que opera en DE+FR+ES con app corporativa)
- Estimado: <2% del universo dealer total, pero dealers de alto volumen (catálogos >500 vehículos)

## Sub-técnicas

### E10.1 — Identificación de apps vía Play Store / App Store search

Búsqueda sistemática en tiendas de apps:

```
Play Store queries:
  "{dealer_name}" android app
  "{dealer_domain}" app
  "{brand_group}" Automobile app

App Store queries:
  Mismo patrón
```

Verificación de autenticidad: el developer de la app debe coincidir con la entidad legal del dealer (nombre del developer en la tienda).

### E10.2 — APK analysis (Android — legal sobre APKs públicos)

Los APKs de apps de Play Store son descargables vía servicios públicos como APKPure, APKMirror, o directamente del Play Store via gplaycli (herramienta open source). El análisis es legal sobre APKs públicos.

Análisis del APK:
1. `apktool d app.apk` → descompila el APK
2. Búsqueda de strings que contengan URLs de API:
   - `https://api.dealer.de/`
   - `https://app-backend.dealer.com/`
   - Path patterns: `/api/v1/`, `/inventory/`, `/vehicles/`
3. Análisis de `AndroidManifest.xml` para dominios permitidos (`network_security_config`)
4. Análisis de archivos de configuración/resources para URLs base de API

### E10.3 — iOS app analysis (IPA)

IPA files requieren extracción de strings del binario Mach-O. Técnica legal:
1. `strings` command sobre el binario Mach-O del IPA
2. Filtrar strings con pattern URL (http/https)
3. Identificar candidates de API backend

Más limitado que APK analysis por arquitectura closed de iOS.

### E10.4 — Request directo al endpoint identificado

Una vez identificado el endpoint:
1. Request sin autenticación primero — muchas apps tienen catálogos públicos sin auth
2. Si requiere API key: buscarla en el APK (strings hardcoded — práctica común en apps pequeñas)
3. Si requiere autenticación real (JWT, OAuth) → E10 marca como `NOT_APPLICABLE` sin auth, escalar a E11

### E10.5 — Documentación técnica pública

Algunos DMS providers publican documentación de su API móvil:
- Swagger/OpenAPI specs accesibles
- Developer portals públicos
- GitHub repos de companion SDKs

Si documentación pública existe → E10 consume la API oficialmente documentada, no via reverse engineering.

## Formato de datos esperado
JSON REST API con estructura propietaria del backend de la app. Normalización via YAML field mapper (mismo patrón que E05/E09).

## Campos extraíbles típicamente
Con API bien documentada: todos los campos críticos + secundarios. Con reverse engineering: Make, Model, Year, Price, ImageURLs, SourceURL (URL de la app/web).

## Base legal
- APK analysis: legal sobre APKs obtenidos de tiendas públicas (no crakeo de DRM ni bypass)
- Acceso a API sin autenticación: equivalente a cualquier client HTTP
- Si API requiere autenticación (OAuth2, JWT): E10 NO accede. Escalar a E11 para obtener acceso legítimo vía contrato B2B.
- Base: `public_api_consumption` para APIs sin auth; `b2b_contract` para APIs con auth vía E11

## Métricas de éxito
- `e10_app_found_rate` — % dealers con app móvil identificada
- `e10_api_extracted_rate` — % apps donde se extrae endpoint API
- `e10_public_api_rate` — % endpoints sin autenticación (accesibles directamente)
- `e10_vehicles_per_app` — catálogo medio de dealers con app

## Implementación
- Módulo Go (wrapper): `services/pipeline/extraction/strategies/e10_mobile_api/`
- Herramientas externas: apktool (Java), strings (sistema), gplaycli (Python)
- Sub-módulo: `app_discovery.go` — búsqueda en Play Store / App Store
- Sub-módulo: `apk_analyzer.go` — subprocess apktool + string analysis
- Sub-módulo: `api_caller.go` — request al endpoint identificado + normalización
- Coste cómputo: medio-alto (APK analysis es CPU intensivo), run ocasional
- Cron: análisis APK mensual por app identificada; API calls diarios una vez endpoint conocido

## Fallback strategy
Si E10 no produce resultado:
- E11 (Edge onboarding) para grupos dealer con app: son candidatos de alto valor para contrato B2B directo

## Riesgos y mitigaciones
- R-E10-1: APK ofuscado (ProGuard, R8) que oculta URLs. Mitigación: strings sobre binario nativo aún puede revelar URLs hardcoded; si completamente ofuscado → skip APK, buscar documentación pública.
- R-E10-2: API requiere autenticación por razones de seguridad legítimas. Mitigación: NO evadir auth. Escalar a E11 para acuerdo B2B.
- R-E10-3: App inactiva (no actualizada en >1 año). Mitigación: verificar `Last updated` en tienda antes de invertir en análisis.
- R-E10-4: API con rate limiting muy agresivo (app diseñada para uso móvil, no scraping). Mitigación: rate limit ultra-conservador; si bloqueo → escalar a E11.

## Iteración futura
- Progressive Web Apps (PWA): algunos dealers usan PWA en lugar de app nativa — los service workers y manifests son más fáciles de analizar
- React Native / Flutter apps: el código JS/Dart en el bundle es más legible que código nativo obfuscado
- Watchdog de nuevas apps: monitoreo automático de Play Store para dealers del knowledge graph que publiquen nueva app
