---
name: APIs externas — estado de credenciales
description: Which external API credentials are available, pending, or public for CARDEX services
type: reference
originSessionId: f40b2fe4-7b98-4b15-bea1-af705c3e870f
---
> NOTA DE SEGURIDAD: este fichero NUNCA contuvo claves en texto plano. Los
> valores reales viven en vault/env. Para la versión que se integra al repo se
> han redactado además identificadores personales (cuenta de email, GCP project
> id, token id) — se preserva QUÉ API existe y su estado, nunca el secreto.

Estado de credenciales a 2026-04-19. Valores reales en vault/env, NUNCA en repo.

**Activas (key disponible):**
- VIES (VAT EU): público, sin key, SOAP endpoint
- YouTube Data API v3: GCP project `<REDACTED-gcp-project-id>`, 10k units/día, cuenta `<REDACTED-account-email>`
- INSEE SIRENE v3.11: activo, 30 req/min, portail-api.insee.fr
- Shodan: free community, cuenta `<REDACTED-account-email>`
- Censys: token regenerado 2026-04-19, nombre "CARDEX TLS Mining", ID `<REDACTED-token-id>`, 1 acción concurrente (Free Plan)
- KvK NL (test): entorno test activo con datos ficticios, key disponible

**Públicas sin autenticación:**
- NHTSA vPIC: VIN decode, sin key
- RDW NL: open data vehicular, sin key
- KBO/BCE BE: portal web público, sin API REST

**Pendientes:**
- Pappers: reset de password enviado a `<REDACTED-account-email>`, pendiente de recepción (100 req/mes free)
- KvK NL (producción): requiere KvK number holandés (empresa registrada en NL). Alternativa: OpenCorporates API

**Config:** `deploy/env.example` tiene template, `workspace/internal/config/config.go` carga de env vars.
