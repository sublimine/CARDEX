# Familia E — DMS hosted infrastructure mapping

## Identificador
- ID: E
- Nombre: DMS hosted infrastructure mapping
- Categoría: Infra-DMS
- Fecha: 2026-04-14
- Estado: DOCUMENTADO

## Propósito y rationale
Muchos dealers (especialmente long-tail) no tienen web propia. Su "presencia web" es una página hospedada por su proveedor de DMS (Dealer Management System). Identificar los rangos IP y patrones URL de los principales DMS hosted providers permite descubrir miles de dealers en una sola integración técnica por proveedor.

Es la palanca de eficiencia: cada DMS hosted provider es un "marketplace dealer-only" que CARDEX puede mapear sistemáticamente.

## DMS providers principales con hosted sites

### E.1 — DealerSocket (Solera)
- Hosted domain pattern: `*.dealersocket.net`, `*.dealersocketdealer.com`
- IP ranges: documentados via reverse PTR + ASN lookup
- URL pattern típico: `dealer-name.dealersocket.net`
- Cobertura geográfica: principal NL, BE, FR

### E.2 — CDK Drive Sites (CDK Global)
- Hosted domain pattern: `*.cdkglobal.com`, `*.cdkglobal-dealersites.com`
- IP ranges: por documentar
- URL pattern: `dealer-name.cdkglobal.com/showroom/`
- Cobertura: DE, FR, ES, NL fuerte

### E.3 — Autobiz Showroom
- Hosted domain pattern: `*.autobiz.com`, `*.autobiz-showroom.com`
- URL pattern: `dealer-name.autobiz.com`
- Cobertura: FR, ES principal

### E.4 — Kerridge K8 Web (KCS)
- Hosted domain pattern: `*.kerridgecs.com`, `*.kcsdealer.com`
- Cobertura: BE, NL, UK

### E.5 — Cox Automotive incadea
- Hosted domain pattern: `*.incadea.com`
- Cobertura: DE, CH, AT principal

### E.6 — Reynolds & Reynolds (Mobility Solutions EU)
- Hosted domain pattern: `*.reyrey.com` (US-origin pero presencia EU)
- Cobertura: limitada en target

### E.7 — GoCar Dealer Sites
- Hosted domain pattern: `*.gocar-sites.com`
- Cobertura: emergente

### E.8 — Manheim Express Listings (sub-sites dealer)
- Algunos dealers exponen perfil hosted con catálogo

### E.9 — White-label aggregators

#### E.9.1 — AutoTrack white-label (NL)
- Algunas dealer sites son AutoTrack-hosted under custom domain
- Detectable por footer "Powered by AutoTrack"

#### E.9.2 — AutoScout24 dealer subsites
- AutoScout24 ofrece subdominios dealer: `dealer-id.autoscout24.de/dealer-page`
- Listado completo via Familia F (aggregator directories)

## Sub-técnicas de mapeo

### E.M1 — Reverse IP lookup
- Servicios free: SecurityTrails (50/día), Hackertarget (50/día), Censys free tier
- Para cada IP de un DMS provider conocido → lista todos los hostnames hospedados
- Cada hostname es un dealer potencial

### E.M2 — ASN enumeration
- Identificar ASN del proveedor DMS via IP
- Tools: BGP.he.net, RIPEstat
- Listar todos los rangos IP del ASN
- Reverse PTR de cada IP

### E.M3 — Certificate Transparency (cross-Familia C.3)
- Buscar SAN entries con dominio del DMS provider
- Captura subdominios dealer no descubiertos por reverse PTR

### E.M4 — Pattern matching en CC-Index (cross-Familia C.1)
- Filtrar URLs en CC-Index que matchen patterns DMS hosted
- Discovery indirecto vía crawl público

## Base legal
- Reverse IP lookup: legal (DNS público)
- ASN enumeration: legal (BGP datos públicos)
- CT logs: público por RFC 6962
- Common Crawl: bajo CC BY 4.0
- Acceso a hosted sites resultantes: igual que cualquier site público (UA transparente, robots.txt, rate limits)

## Métricas

- `dms_providers_mapped` — proveedores DMS con infra mapeada
- `dealers_discovered_per_dms(provider)` — dealers únicos por provider
- `extraction_success_rate_per_dms(provider)` — % dealers extraíbles del total descubiertos
- `cross_validation_with_C(país)` — overlap con dominios de Familia C

## Implementación

- Módulo Go: `discovery/family_e/`
- Sub-módulos: por DMS provider (`dealersocket/`, `cdk/`, `autobiz/`, `kerridge/`, `incadea/`, etc.)
- Persistencia: SQLite tabla `dms_hosted_dealers` + `dms_provider_inventory`
- Cron: full sweep mensual + sync incremental semanal
- Coste cómputo: bajo en sweep inicial, medio en sync (rate-limited por free tiers)
- Dependencias: cliente DNS Go, integración con Censys API free tier, BGP datasource

## Cross-validation con otras familias

| Otra familia | Overlap | Discovery único de E |
|---|---|---|
| C | ~60% | E captura dealers cuyo "site" es un subdomain DMS no detectado en CC |
| D | inverso (ver D) | D detecta CMS propio; E detecta hosting compartido |
| F | ~40% | E captura dealers no perfilados en aggregator |

## Riesgos y mitigaciones

- **R-E1:** Free tier limits agresivos en SecurityTrails/Censys. Mitigación: priorizar providers de mayor cobertura, distribuir queries en el tiempo.
- **R-E2:** DMS providers cambian de hosting infra. Mitigación: re-mapeo trimestral.
- **R-E3:** White-label complejo (dominio custom encima de hosted). Mitigación: detección por footer/JS signatures (cross-Familia D).
- **R-E4:** Algunos DMS hosted requieren auth para ver inventario completo. Mitigación: marcar como "extracción parcial", input para Edge dealer onboarding (Fase 11 plan).

## Iteración futura

- Mapeo de DMS providers regionales menores (cada país tiene proveedores locales no listados aquí)
- Análisis de migraciones DMS (un dealer cambió de CDK a DealerSocket → indicador útil)
- Integración con OEM-specific DMS (algunas marcas obligan a sus dealers a usar un DMS específico)
