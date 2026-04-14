# Familia N — Network/infrastructure intelligence

## Identificador
- ID: N, Nombre: Network/infrastructure intelligence, Categoría: Infra-recon
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Descubre relaciones infrastructurales entre entidades: sites hospedados en la misma IP (DMS shared, dealer chain), subdominios compartidos, certificados SSL con múltiples dealers en SAN, proveedores de hosting comunes. Aporta visibility sobre estructuras dealer multi-location que a nivel UI son invisibles pero a nivel infra son obvias.

## Fuentes

### N.1 — Censys Free Tier
- URL: https://search.censys.io
- Free tier: 250 queries/mes
- Datos: banners TLS/HTTP, certificados, servicios, hosts
- Uso: reverse IP, certificate SAN search, host enumeration

### N.2 — Shodan Free Tier
- URL: https://www.shodan.io
- Free: 100 results/mes + $1 one-time $49 lifetime
- Datos: banners servicios, hosts, ASNs
- Uso: reverse IP, enumeración de hosting providers

### N.3 — crt.sh (Certificate Transparency) — cross-Familia C.3
- URL: https://crt.sh
- Datos: certificados SSL/TLS emitidos
- SAN (Subject Alternative Name) entries → discovery de subdominios y dominios hermanos
- Totalmente gratis y sin límite efectivo

### N.4 — Passive DNS providers (cross-Familia C.4)
- SecurityTrails free (50/día)
- VirusTotal free (limited)
- Hackertarget free (50/día)
- DNSDumpster (HTML público gratis)

### N.5 — BGP.he.net / Hurricane Electric
- URL: https://bgp.he.net
- Datos: ASN → rangos IP asignados → hosts en esos rangos
- Gratis, sin límite
- Uso: enumerar infraestructura de un ISP/proveedor hosting

### N.6 — RIPEstat
- URL: https://stat.ripe.net
- API gratis, datos completos de routing BGP
- Uso: análisis de rutas de IP, identificación de proveedores

### N.7 — OTX AlienVault
- URL: https://otx.alienvault.com
- Free con cuenta
- Datos: indicators of compromise (útil para filtrar hosts maliciosos del knowledge graph)

### N.8 — MaxMind GeoLite2
- Base de datos free con geo+ASN de IPs
- Descarga mensual bulk
- Uso: georreferenciación técnica de hosts dealer

### N.9 — IPInfo Free Tier
- 50k queries/mes gratis
- Geo + ASN + organization

### N.10 — WhoisXMLAPI free tier
- WHOIS data structured
- Limited free tier

## Sub-técnicas

### N.M1 — Certificate SAN mining
Para cada dominio dealer conocido, fetch del certificado SSL + extracción de todos los SAN entries. Cada SAN adicional es un subdominio/dominio hermano potencial que puede ser otro dealer o ubicación de la misma chain.

### N.M2 — Reverse IP enumeration
Para cada IP hosting un dealer conocido, reverse lookup de todos los hostnames que comparten esa IP. Shared hosting → pueden ser dealers del mismo DMS provider (cross-Familia E) o simplemente unrelated. Cross-validación con familia A/C para confirmar dealer identity.

### N.M3 — ASN clustering
Identificar ASNs donde se concentran dealers (hosting providers populares en el sector auto). Mapear el rango IP del ASN + reverse PTR = discovery masivo.

### N.M4 — Subdomain enumeration per dealer-root-domain
Para cada dominio raíz dealer conocido (ej. `bigdealer.de`), enumerar subdominios:
- Vía CT logs (crt.sh)
- Vía passive DNS
- Vía brute-force de prefijos comunes (`www.`, `occasion.`, `gebraucht.`, `nuevos.`, `stock.`, `shop.`)

Captura estructura multi-location dentro de un mismo grupo dealer (subdominios por ciudad: `muenchen.bigdealer.de`, `berlin.bigdealer.de`).

### N.M5 — WHOIS historical mining
Registrant info histórico → identificación de grupos dealer con múltiples dominios registrados por la misma entidad (grupo corporativo oculto tras múltiples brand-names).

## Base legal
- Censys/Shodan free tiers: dentro de su licensing
- CT logs: público por RFC 6962
- Passive DNS: datasets agregados de telemetry consentida
- BGP.he.net/RIPEstat: datos routing BGP públicos
- WHOIS: público (GDPR limita PII de registrants personas físicas — respetar)

## Métricas
- `subdomain_depth_per_dealer` — subdominios descubiertos por dominio raíz
- `multi_dealer_ip_clusters` — IPs hospedando >N dealers (indicador DMS compartido)
- `dealer_chain_discoveries` — grupos dealer multi-location identificados
- `cross_validation_with_E` — overlap con DMS hosted infrastructure

## Implementación
- Módulo Go: `discovery/family_n/`
- Sub-módulos: `censys/`, `shodan/`, `crtsh/`, `passive_dns/`, `bgp/`, `whois/`
- Persistencia: tabla `infra_intelligence` con relaciones (dominio → IP → ASN → organization)
- Cron: mensual (rate limits restrictivos hacen infeasible más frecuente)
- Coste: bajo en compute, limitado en queries API

## Cross-validation

| Familia | Overlap | Único de N |
|---|---|---|
| C (web) | ~50% | N descubre subdominios y hermanos no linkados |
| E (DMS) | ~60% | N confirma mapping infra DMS y descubre providers menores |
| A | bajo | N aporta ortogonal: infra, no legal |

## Riesgos y mitigaciones
- R-N1: free tiers API muy limitados. Mitigación: priorizar queries de alto valor, rotar entre providers.
- R-N2: falsos positivos (hosting compartido no implica relación dealer). Mitigación: confirmación cruzada con familias A/C/F.
- R-N3: WHOIS post-GDPR con datos redactados. Mitigación: usar cuando disponible, no bloquear pipeline si no lo está.

## Iteración futura
- Integración de ZoomEye, FOFA cuando free tiers estén disponibles para EU users
- Análisis de fingerprints JARM/JA3 para clustering de dealers con mismo stack (sin evadir, solo fingerprint passive)
- Monitoreo de cambios infra como señal de transición (dealer cambia de hosting → signal de cambio corporativo)
