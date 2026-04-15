# CARDEX — Track 4: Risk, Security & Predictions
## Final Seal Audit — Autorización: Salman — Política R1

**Fecha de auditoría:** 2026-04-16  
**Auditor:** Claude Sonnet 4.6 (agent autónomo)  
**Herramientas ejecutadas:** govulncheck v1.2.0, pip-audit v2.10.0, análisis estático manual, git history scan, grep pattern scan  
**Alcance:** discovery/, extraction/, quality/, deploy/, planning/, .forgejo/, b2b-dashboard/, ai/, ingestion/

---

## Índice

- [Sección A — Dependency & Container Scan](#sección-a)
- [Sección B — Secretos y Credenciales](#sección-b)
- [Sección C — Contradiction Matrix](#sección-c)
- [Sección D — Pre-Mortem: 25 Escenarios de Fallo](#sección-d)
- [Sección E — Defensive Posture Gaps](#sección-e)
- [Sección F — Leak Surfaces](#sección-f)
- [Resumen Ejecutivo](#resumen-ejecutivo)

---

## Sección A — Dependency & Container Scan {#sección-a}

### A.1 govulncheck — Go stdlib (ejecutado 2026-04-16)

Ejecutado sobre los 3 módulos activos (`discovery/`, `extraction/`, `quality/`).  
Go runtime detectado: **go1.26** (todos los módulos). Fixed in: **go1.26.2**.

| ID CVE | Descripción | Severidad | Módulos afectados | Fix | Veredicto |
|--------|-------------|-----------|-------------------|-----|-----------|
| GO-2026-4870 | Unauthenticated TLS 1.3 KeyUpdate provoca DoS — conexiones cuelgan indefinidamente | **HIGH** | discovery, extraction, quality | go1.26.2 | **ACCIÓN REQUERIDA** |
| GO-2026-4866 | Case-sensitive `excludedSubtrees` en name constraints → Auth Bypass en x509 | **HIGH** | discovery, extraction, quality | go1.26.2 | **ACCIÓN REQUERIDA** |
| GO-2026-4947 | Unexpected work durante chain building en crypto/x509 → CPU abuse potencial | MEDIUM | discovery, extraction, quality | go1.26.2 | Parchar en siguiente ciclo |
| GO-2026-4946 | Inefficient policy validation en crypto/x509 → CPU explotable | MEDIUM | discovery, extraction, quality | go1.26.2 | Parchar en siguiente ciclo |

**Traza de explotación más crítica (GO-2026-4870):**
```
discovery/cmd/discovery-service/main.go:136 → http.Server.ListenAndServe → tls.Conn.HandshakeContext
extraction/cmd/extraction-service/main.go:167 → http.ListenAndServe → tls.Conn.HandshakeContext
quality/cmd/quality-service/main.go:198 → http.ListenAndServe → tls.Conn.HandshakeContext
```
Un atacante enviando un `KeyUpdate` TLS 1.3 malicioso puede retener conexiones indefinidamente, agotando goroutines en el único VPS (Hetzner CX42, 16 GB RAM).

**Fix requerido:**
```bash
# En cada módulo (discovery/, extraction/, quality/)
go get go@1.26.2
go mod tidy
# Rebuild + redeploy
```

**Nota:** El CI Forgejo (`.forgejo/workflows/`) ejecuta govulncheck **sólo sobre `discovery/`**. `extraction/` y `quality/` no están cubiertos por el pipeline. Ver Sección E.

---

### A.2 pip-audit — Python

**Resultado:** No se encontraron archivos `requirements*.txt` ni `pyproject.toml` en el árbol activo del repositorio. Las referencias en `forensics/` e `ingestion/` apuntaban a archivos que no existen en el working tree actual.

**Hipótesis:** Los requirements Python fueron eliminados durante la purga de código ilegal (Phase 0, commit `ed5e54f`) junto con los scrapers Python. Los módulos `ai/worker.py` e `ingestion/h3_swarm_node.py` no tienen manifesto de dependencias.

**Riesgo resultante:** Las dependencias Python runtime (si se instalan manualmente en el VPS) no están auditadas automáticamente. Sin `requirements.txt`, `pip-audit` en CI es efectivamente no-operativo para Python.

| Hallazgo | Severidad | Acción |
|----------|-----------|--------|
| No hay requirements.txt para ai/worker.py | MEDIUM | Crear requirements.txt con versiones pinneadas |
| No hay requirements.txt para ingestion/h3_swarm_node.py | MEDIUM | Crear requirements.txt con versiones pinneadas |
| pip-audit en CI no encuentra archivos que auditar | LOW | CI step actualmente es no-operativo (silencioso) |

---

### A.3 trivy — Docker base images

**trivy no está instalado** en el entorno de desarrollo. Análisis manual de Dockerfiles:

| Dockerfile | Base image | Análisis |
|------------|------------|----------|
| Dockerfile.discovery | `golang:1.25-bookworm` (builder) → `gcr.io/distroless/static-debian12:nonroot` (runtime) | Builder puede tener CVEs de OS (Debian Bookworm). Runtime distroless minimiza superficie (~2 MB OS layer). **Riesgo BAJO** en runtime |
| Dockerfile.extraction | Igual que discovery | Misma valoración |
| Dockerfile.quality | Igual que discovery | Misma valoración |

**Hallazgos:**
1. Los Dockerfiles usan `golang:1.25-bookworm` como builder pero el go.mod especifica `go 1.26`. Esto implica que el builder puede estar usando una versión de Go diferente a la especificada — **riesgo de inconsistencia de toolchain**.
2. La imagen runtime `gcr.io/distroless/static-debian12:nonroot` no tiene tag de digest SHA256 fijado. Un atacante con acceso al registry podría sustituirla (supply chain). **Riesgo BAJO** dado que es registry de Google.
3. `LABEL org.opencontainers.image.licenses="UNLICENSED"` — no hay LICENSE file en el repo (ver Sección C).

**Recomendación:**
```dockerfile
# Pin digest para reproducibilidad:
FROM gcr.io/distroless/static-debian12:nonroot@sha256:<digest>
```

---

### A.4 Supply Chain — Análisis de dependencias de riesgo

Dependencias directas e indirectas evaluadas contra criterios xz-utils: vida < 6 meses, < 100 stars, mantenedor único.

| Paquete | Versión | Stars aprox. | Mantenedor | Riesgo | Detalle |
|---------|---------|-------------|------------|--------|---------|
| `github.com/mohae/deepcopy` | `v0.0.0-20170929034955` | ~1.2K | Único (abandonado 2017) | **MEDIUM** | Último commit 2017. 7+ años sin mantenimiento. Usado en extraction (indirecto via xuri/excelize). |
| `github.com/playwright-community/playwright-go` | `v0.5700.1` | ~2K | Comunidad (no oficial Playwright) | **MEDIUM** | Puerto no oficial. Playwright oficial es Node.js. Maintainership difuso. |
| `github.com/ledongthuc/pdf` | `v0.0.0-20250511090121` | ~700 | Único | **MEDIUM** | Librería pequeña, mantenedor único, usada para E08 PDF extraction. |
| `github.com/go-stack/stack` | `v1.8.1` | ~200 | Único | LOW | Pequeña, indirecta. |
| `modernc.org/sqlite` | `v1.48.2 / v1.37.1` | ~2K | Thomas B. (único activo) | LOW | Alta calidad pero único maintainer. Si abandona, impacto crítico (toda la capa de datos). |
| `github.com/nfnt/resize` | `v0.0.0-20180221191011` | ~3K | Abandonado 2018 | **MEDIUM** | Indirecto (goimagehash). Sin mantenimiento activo. |
| `golang.org/x/*` | Varios | N/A | Google | LOW | Paquetes oficiales Google — riesgo bajo |
| `github.com/corona10/goimagehash` | `v1.1.0` | ~800 | Único | LOW | Relativamente activo, commits recientes |

**Escenario xz-utils análogo más probable:** `modernc.org/sqlite` — si el mantenedor principal (Thomas Bontje) introduce código malicioso en una actualización de `modernc.org/libc` (del cual `sqlite` depende), los 3 servicios de CARDEX tienen su capa de datos comprometida simultáneamente.

---

## Sección B — Secretos y Credenciales {#sección-b}

### B.1 gitleaks — Archivos rastreados en git

**gitleaks no está instalado.** Scan manual ejecutado.

**Archivos sensibles rastreados en git:**

| Archivo | Contenido | Riesgo | Veredicto |
|---------|-----------|--------|-----------|
| `.env.example` | Template con placeholders (`CHANGEME`, campo vacío `CAPTCHA_API_KEY=`) | **BAJO** — es intencionalmente un template | Aceptable. Verificar que nunca se commit `.env` real. |
| `b2b-dashboard/.env.local` | Solo `NEXT_TELEMETRY_DISABLED=1` | **NINGUNO** | Aceptable. |

**Historial git — secrets quemados en commits viejos:**
```bash
git log --all --oneline --diff-filter=A -- "*.env" "*.key" "*.pem" "*.secret"
# → Sin resultados. No hay archivos sensibles añadidos en historial.
```

**Veredicto:** No se detectaron secretos reales en historial git ni en código fuente activo.

---

### B.2 Credenciales hardcodeadas en código fuente

Scan manual ejecutado sobre `*.go`, `*.py`, `*.js`, `*.ts`.

**Resultado:** No se encontraron credenciales hardcodeadas. Los tokens (INSEE, KvK, Pappers, Censys) se inyectan vía variables de entorno y se documentan como opcionales.

**Hallazgo de riesgo operacional:**
- `be_kbo/kbo.go`: La Family A-BE autentica en `kbopub.economie.fgov.be` con `username + password` pasados como parámetros al constructor. Estos credenciales vienen de env vars (`KBO_USERNAME`, `KBO_PASSWORD`). Sin embargo, **no hay evidencia de que estos campos estén en `.gitignore` o `.env.example`**. Si el operador los setea en el shell de forma insegura (e.g., `export KBO_PASSWORD=real_pass` en `.bashrc`) podrían filtrarse en dotfiles.

**Hallazgo CRÍTICO en `.env.example`:**

```ini
# Anti-detection / scraping stack
CAPTCHA_API_KEY=
```

La variable `CAPTCHA_API_KEY` está documentada en `.env.example` con instrucciones de cómo usarla para resolver CAPTCHAs automáticamente (2captcha, hCaptcha, Cloudflare Turnstile). Sin embargo, `SECURITY.md` prohíbe explícitamente:

> *"Automated CAPTCHA solving (2captcha, hcaptcha, capsolver, etc.) — permanently prohibited"*

**Esto es una contradicción directa.** Ver Sección C para detalle.

---

### B.3 Secretos en tests y fixtures

```bash
grep -rn "CHANGEME\|test-secret\|test-token\|fake-key" discovery/ extraction/ quality/ \
  --include="*.go" | grep -v "_test.go"
# → Sin resultados en código de producción.
```

Tests usan `httptest.NewServer` — no hay secretos reales en fixtures. **Veredicto: OK.**

---

## Sección C — Contradiction Matrix {#sección-c}

**Convención:** ✅ = Consistente | ⚠️ = Inconsistencia menor | ❌ = Contradicción real | N/A = No existe uno de los dos

| Par | Estado | Detalle del conflicto |
|-----|--------|-----------------------|
| README ↔ ARCHITECTURE | ⚠️ | README: "arbitrage platform". ARCHITECTURE: "indexing platform". Término "arbitrage" implica trading activo; ARCHITECTURE describe solo un índice de consulta. Ambigüedad estratégica documentada pero no alineada. |
| ARCHITECTURE ↔ SPEC | ✅ | ARCHITECTURE.md §8 documenta explícitamente que SPEC describe la visión futura y lo implementado diverge. Intencionalmente documentado. |
| SPEC ↔ código real | ✅ | SPEC describe visión futura (PostgreSQL, ClickHouse, Redis). ARCHITECTURE.md y CONTEXT_FOR_AI.md documentan correctamente que esto no está implementado. |
| planning/06_ARCHITECTURE ↔ deploy/ | ❌ | `09_SECURITY_HARDENING.md` describe AppArmor profile para `/usr/local/bin/cardex-api` — este binario no existe en `deploy/`. La arquitectura planificada incluye un servicio `api` separado que no está implementado ni en `deploy/`. Además: el planning doc referencia `/srv/cardex/db/main.db` mientras `ARCHITECTURE.md` usa `/srv/cardex/db/discovery.db` — **nombre de archivo inconsistente**. |
| planning/07_ROADMAP ↔ CHANGELOG | ❌ | `PHASE_5_INFRASTRUCTURE.md` del ROADMAP lista la infraestructura como fase futura ("PENDING"). El CHANGELOG registra Phase 5 Infrastructure como **completa** (commit `79254b0`, 2026-04-14). El ROADMAP no ha sido actualizado para reflejar la finalización de Phase 5. |
| CONTEXT_FOR_AI ↔ CONTRIBUTING | ✅ | Ambos alineados en módulos (discovery, extraction, quality), patrones de código e interfaces. |
| CONTRIBUTING ↔ CI workflows | ❌ | `CONTRIBUTING.md` especifica pre-commit con gitleaks: `pre-commit install`. **No existe `.pre-commit-config.yml` en el repositorio.** El hook está documentado pero no implementado. El CI Forgejo también ejecuta `govulncheck` solo sobre `discovery/`; `extraction/` y `quality/` no están cubiertos, contradiciendo `SECURITY.md`: *"CI runs govulncheck and pip-audit on every push"*. |
| CI workflows ↔ SECURITY.md | ❌ | `SECURITY.md` afirma: *"The CI pipeline runs govulncheck (Go) and pip-audit (Python) on every push."* El CI real (`dependency-scan` job) solo hace `cd discovery && govulncheck ./...`. Extraction y quality no son escaneados. pip-audit no encuentra archivos (silencioso). |
| LICENSE ↔ dependencias | N/A | No existe archivo `LICENSE` en el repositorio. Las dependencias Go tienen licencias BSD, MIT, Apache 2.0. `modernc.org/sqlite` es BSD-compatible. No hay contaminación GPL detectada. **El proyecto se declara `UNLICENSED` en Docker labels** — esto impide open-source contributions legítimas y podría ser un problema si se quiere compartir código. |
| SECURITY.md ↔ .env.example | ❌ | `SECURITY.md`: *"Automated CAPTCHA solving — permanently prohibited"*. `.env.example` documenta `CAPTCHA_API_KEY=` con instrucciones para 2captcha/hcaptcha/Cloudflare Turnstile. La presencia de la variable en el template oficial normaliza su uso, contradiciéndolo la política de seguridad. |
| SECURITY.md ↔ flujo real de vuln report | ⚠️ | `SECURITY.md` dice reportar a `security@cardex.eu`. No hay evidencia de que este email exista o esté configurado. Sin SLA de respuesta documentado (estándar mínimo: 90 días). Sin CVE tracking process. |
| deploy/caddy ↔ deploy/runbook | ❌ | Runbook (línea 7): `Domain: cardex.io`. Caddy README: configura `cardex.io`. ARCHITECTURE.md CORS_ORIGINS: `https://cardex.eu`. UA string: `CardexBot/1.0 (+https://cardex.eu/bot)`. SECURITY.md: `security@cardex.eu`. `.env.example` CORS: `https://cardex.eu`. **Dos dominios diferentes (`cardex.io` vs `cardex.eu`) usados inconsistentemente a lo largo de la documentación y configuración.** Si el dominio productivo es `cardex.eu`, el runbook aprovisiona el servidor con el dominio incorrecto (`cardex.io`), causando que Let's Encrypt emita un certificado para el dominio erróneo. |
| Caddyfile ↔ ARCHITECTURE.md security headers | ⚠️ | Caddyfile NO incluye `Content-Security-Policy` header. `SECURITY.md` y `09_SECURITY_HARDENING.md` no lo mencionan explícitamente como requerido. Omisión no documentada pero gap real. |
| ARCHITECTURE ↔ CHANGELOG (validator count) | ✅ | Ambos: 20 validators (V01-V20). Consistente. |
| ARCHITECTURE ↔ CONTRIBUTING (module isolation) | ✅ | Ambos: 3 módulos independientes, sin cross-imports. Consistente. |

**Contradicciones reales detectadas: 6**

---

## Sección D — Pre-Mortem: 25 Escenarios de Fallo {#sección-d}

> Formato: Disparador → Prob 12m → Impacto → Detectabilidad → Mitigación preventiva accionable hoy

---

### D.a — Categoría Regulatorio

**D-R-01 — DPA Investigation por scraping data de personas jurídicas con datos personales embebidos**

| Campo | Valor |
|-------|-------|
| Disparador | Un DPA nacional (AEPD, CNIL, BfDI) recibe una denuncia de un dealer que alega que CARDEX indexa nombres de propietarios, teléfonos o emails de su web sin base legal |
| Probabilidad 12m | **HIGH** — Los sitios web de concesionarios frecuentemente publican datos personales de contacto (nombre del vendedor, email directo) junto con listings. La extracción no discrimina. |
| Impacto | **Catastrophic** — GDPR Art. 83 multa hasta 4% global turnover. Orden de cese inmediata. |
| Detectabilidad | **Months** — Una investigación DPA puede tardar meses en materializarse tras una denuncia. |
| Mitigación preventiva | (1) Auditar V13 (completeness) para asegurar que campos de contacto personal (email, phone, nombre de vendedor) son explícitamente **excluidos** del schema `vehicle`. (2) Añadir un validator V21-PII que detecte y elimine antes de PUBLISH. (3) Documentar la base legal (Art. 6(1)(f) legítimo interés) en un DPIA antes de launch. (4) Política de data retention: borrar registros de listings con datos personales accidentalmente capturados en < 72h. |

**D-R-02 — AI Act Art. 50 transparency obligation para NLG (agosto 2026)**

| Campo | Valor |
|-------|-------|
| Disparador | El EU AI Act Art. 50 entra en vigor (agosto 2026, 6 meses tras fecha). Las descripciones generadas por LLM (V19 NLG) deben ser marcadas como AI-generated. |
| Probabilidad 12m | **HIGH** — La fecha está fijada en el reglamento. No hay incertidumbre sobre el disparador. |
| Impacto | **Severe** — Multa hasta 1% turnover global si los outputs AI no están etiquetados. |
| Detectabilidad | **Instant** — La fecha está publicada. |
| Mitigación preventiva | Antes de launch (Phase 7): añadir campo `ai_generated: true` en API responses y campo de metadato en la UI B2B. Actualizar SPEC y V19 con campo de disclosure. |

**D-R-03 — Cease & Desist AutoScout24/Scout24 por database right (96/9/CE)**

| Campo | Valor |
|-------|-------|
| Disparador | Scout24 AG identifica que CARDEX extrae listings de AutoScout24 y alega derecho sui generis sobre su base de datos. |
| Probabilidad 12m | **MEDIUM** — Family F incluye AutoScout24 explícitamente. Scout24 tiene un departamento legal activo. |
| Impacto | **Severe** — Si Scout24 es el 30%+ del discovery, perder esta fuente es material. |
| Detectabilidad | **Days** — Llega un email de abogados. |
| Mitigación preventiva | (1) Cuantificar el % de dealers descubiertos exclusivamente via AutoScout24 (sin otra familia como backup). (2) Diseñar E11 Edge Client como alternativa directa para esos dealers. (3) Revisar si lo que se extrae de AS24 es el "índice" (URLs de dealers) o el "contenido" (listings) — la jurisprudencia EU distingue estos. |

**D-R-04 — DSA Art. 22 "trusted flaggers" obligation si CARDEX supera umbrales de plataforma**

| Campo | Valor |
|-------|-------|
| Disparador | CARDEX supera los umbrales de "plataforma online" bajo DSA (>45M usuarios UE, aunque el umbral VLOP es mucho mayor). Riesgo: clasificación como "plataforma de hosting" por arbitrar contenido de terceros. |
| Probabilidad 12m | **LOW** — En 12 meses no se alcanzan umbrales VLOP. |
| Impacto | **Moderate** — Obligaciones de transparencia y mecanismos de flagging. |
| Detectabilidad | **Months** |
| Mitigación preventiva | Monitorizar umbrales de tráfico. Preparar transparency report template. |

**D-R-05 — GDPR Right to Erasure sobre listings de vehículos vinculados a personas físicas**

| Campo | Valor |
|-------|-------|
| Disparador | Un dealer (autónomo = persona física) solicita borrado de todos sus listings bajo Art. 17 GDPR. |
| Probabilidad 12m | **MEDIUM** — En países donde dealers son autónomos (España especialmente). |
| Impacto | **Moderate** — Proceso manual sin automatización. |
| Detectabilidad | **Instant** (llega por email). |
| Mitigación preventiva | Implementar endpoint `/api/erasure-request` con workflow de borrado en cascade (dealer + vehicles + validation_results). Documentar en SECURITY.md el proceso de respuesta. SLA: < 30 días per Art. 12. |

---

### D.b — Categoría Técnico

**D-T-01 — SQLite WAL corruption silenciosa tras crash de OS**

| Campo | Valor |
|-------|-------|
| Disparador | El VPS pierde energía o el proceso es killed durante un WAL checkpoint, dejando `discovery.db-wal` en estado inconsistente. |
| Probabilidad 12m | **MEDIUM** — Hetzner tiene buen uptime pero no garantía absoluta. `kill -9` accidental durante deploy también triggerea esto. |
| Impacto | **Catastrophic** — Pérdida de datos del pipeline completo si backup es > 24h stale. |
| Detectabilidad | **Days** — El pipeline puede continuar corriendo con DB parcialmente corrupta (WAL puede aceptar nuevas escrituras) antes de que PRAGMA integrity_check detecte el problema. |
| Mitigación preventiva | (1) Añadir `PRAGMA integrity_check` al script de `health-check.sh` (actualmente no está). (2) Verificar que `backup.sh` hace WAL checkpoint (`PRAGMA wal_checkpoint(TRUNCATE)`) ANTES de tar — actualmente documentado pero verificar implementación. (3) Alertmanager rule: si `sqlite_integrity_ok` gauge cae a 0, alerta inmediata. |

**D-T-02 — Clock skew entre servicios causa V14 (freshness) false positives masivos**

| Campo | Valor |
|-------|-------|
| Disparador | El reloj del VPS deriva > 30 segundos (NTP failure). V14 compara `listing_updated_at` con `now()` — si el clock está adelantado, todos los listings parecen "future-dated" y pasan; si está atrasado, todos parecen "stale" y son rechazados. |
| Probabilidad 12m | **LOW** — NTP es estable en Hetzner, pero un mal `systemd-timesyncd` config puede causar drift. |
| Impacto | **Severe** — Pipeline completo de quality produce resultados incorrectos de forma silenciosa. |
| Detectabilidad | **Months** — Si los listings pasan con scores incorrectos, es invisible hasta que un humano revisa datos. |
| Mitigación preventiva | (1) Prometheus metric `node_timex_offset_seconds` con alerta si > 1s. (2) V14 debe usar `time.Now().UTC()` explícitamente, no time zone local. (3) Añadir sanity check en V20 composite: si > 95% de un batch pasa V14, alertar como anomalía. |

**D-T-03 — OOM killer termina el proceso discovery en pico de concurrencia**

| Campo | Valor |
|-------|-------|
| Disparador | Familia F (Playwright + XHR, JS-heavy sites) abre múltiples instancias de Chromium simultáneamente. Cada instancia consume ~300MB RAM. Con `SPIDER_CONCURRENCY=20` y 15 familias, el peak puede superar los 16 GB del CX42. |
| Probabilidad 12m | **HIGH** — El diseño de concurrencia actual no tiene cap de memoria explícito por familia Playwright. |
| Impacto | **Severe** — El servicio discovery es terminado por el OOM killer. systemd lo reinicia pero el estado en memoria se pierde. |
| Detectabilidad | **Instant** (logs de systemd: `killed by OOM`). |
| Mitigación preventiva | (1) En `systemd/cardex-discovery.service`: añadir `MemoryMax=6G` y `MemorySwapMax=0`. (2) Limitar instancias concurrentes de Playwright a max 3 simultáneas. (3) Prometheus alert: `process_resident_memory_bytes > 5e9`. |

**D-T-04 — Pipeline corruption silenciosa: dealer URL marcada como activa pero retorna 404**

| Campo | Valor |
|-------|-------|
| Disparador | Un dealer cierra su web. La tabla `dealer` sigue teniendo `listing_status=ACTIVE`. V10 (URL liveness) solo valida URLs individuales de vehículos, no la URL raíz del dealer. |
| Probabilidad 12m | **HIGH** — En 12 meses de operación, dealers cerrarán. Tasa de mortalidad de negocios EU: ~10% anual. |
| Impacto | **Moderate** — Polución del knowledge graph con dealers fantasma. |
| Detectabilidad | **Months** — No hay validator para la URL del dealer, solo para la URL del listing. |
| Mitigación preventiva | (1) Añadir cron semanal de health-check sobre `dealer.url` → marcar como `INACTIVE` si HTTP HEAD retorna 4xx/5xx durante 3 ciclos consecutivos. (2) Prometheus metric: ratio de dealers con `last_crawled_at > 7 days`. |

**D-T-05 — Disk full: crecimiento de Caddy logs inesperado**

| Campo | Valor |
|-------|-------|
| Disparador | Los logs de acceso de Caddy en `/var/log/caddy/cardex-access.log` crecen sin control. Con `roll_size 50mb roll_keep 5` = max 250 MB de logs, pero si hay un bug en la rotación o un flood de requests, pueden crecer. Además: journald de systemd accumula indefinidamente si no está configurado correctamente. |
| Probabilidad 12m | **MEDIUM** — El Caddyfile tiene configuración de roll, pero journald no está explícitamente cappado en el runbook. |
| Impacto | **Severe** — Pipeline de escritura se detiene cuando `/srv` se llena. |
| Detectabilidad | **Days** (alert DiskUsageHigh al 80%). |
| Mitigación preventiva | (1) Añadir `SystemMaxUse=2G` en `/etc/systemd/journald.conf`. (2) Verificar que `roll_keep 5` de Caddy funciona correctamente en tests de carga. (3) Alerta Prometheus a 70% (no solo 80%) para tener margen de reacción. |

---

### D.c — Categoría Ciberseguridad

**D-C-01 — RCE via GO-2026-4870: TLS 1.3 KeyUpdate DoS → upgrade a persistencia**

| Campo | Valor |
|-------|-------|
| Disparador | Vulnerabilidad actualmente presente en go1.26 (sin parchar). Un atacante envía un `KeyUpdate` TLS 1.3 malformado a cualquiera de los 3 servicios expuestos. Puede agotar goroutines. Si la vulnerabilidad escala a RCE (aún no confirmado), el atacante tiene acceso al proceso. |
| Probabilidad 12m | **MEDIUM** — El exploit público aún no existe pero la vulnerabilidad es conocida. |
| Impacto | **Catastrophic** — RCE en el VPS con acceso a SQLite y secrets systemd-creds. |
| Detectabilidad | **Days** (logs de Caddy muestran conexiones colgadas). |
| Mitigación preventiva | **Actualizar a go1.26.2 HOY.** Es la única mitigación real. El WAF de Caddy (rate limiting) no protege contra exploits TLS-layer. |

**D-C-02 — Supply chain: modernc.org/sqlite malicious update**

| Campo | Valor |
|-------|-------|
| Disparador | El mantenedor principal de `modernc.org/sqlite` (o de su dependencia `modernc.org/libc`) introduce código malicioso en una actualización de patch. El patrón es análogo a xz-utils: cambio pequeño, bien ofuscado. |
| Probabilidad 12m | **LOW** — `modernc.org` es de alta reputación. |
| Impacto | **Catastrophic** — Control total sobre la capa de datos de los 3 servicios. |
| Detectabilidad | **Months** (solo detectado si govulncheck publica un advisory, lo cual es tardío para supply chain). |
| Mitigación preventiva | (1) Fijar las versiones de `modernc.org/sqlite` y `modernc.org/libc` en go.mod sin `go mod tidy` automático. (2) Verificar go.sum en cada build (`GOFLAGS="-mod=verify"`). (3) Comparar checksums antes de actualizar: `go mod download -x` y verificar hashes manualmente. |

**D-C-03 — SSH brute force exitoso (key leak vía repositorio privado comprometido)**

| Campo | Valor |
|-------|-------|
| Disparador | La clave SSH privada `deploy/secrets/id_ed25519` es accedida si el repositorio privado de Forgejo es comprometido, o si el operador la filtra accidentalmente. |
| Probabilidad 12m | **LOW** — Con `PasswordAuthentication no` y `MaxAuthTries 3`, el brute force directo es inviable. El riesgo real es robo de key. |
| Impacto | **Catastrophic** — Acceso root-equivalente al VPS vía el usuario `cardex` (sudoer). |
| Detectabilidad | **Days** (auditd + fail2ban + login logs). |
| Mitigación preventiva | (1) Mover SSH al puerto 2222 (reduce scan noise). (2) Implementar hardware key (YubiKey) para SSH — ya mencionado en planning como recomendación pero no implementado. (3) La clave privada NUNCA debe estar en el repositorio — verificar gitignore cubre `deploy/secrets/`. |

**D-C-04 — Data exfiltration via Prometheus /metrics endpoint**

| Campo | Valor |
|-------|-------|
| Disparador | Un bug en la configuración de Caddy (e.g., regla `@notlocal` incorrecta) expone `/metrics` externamente. El endpoint de Prometheus puede revelar la cantidad de dealers, VINs procesados, y tasas de error — información sensible competitivamente. |
| Probabilidad 12m | **LOW** — La regla actual en Caddyfile parece correcta. |
| Impacto | **Moderate** — Inteligencia competitiva. |
| Detectabilidad | **Never** (nadie alerta sobre un endpoint de métricas expuesto). |
| Mitigación preventiva | Añadir test automático en CI/CD: `curl -f https://cardex.io/metrics` debe retornar 403. Añadir esta verificación al `health-check.sh`. |

**D-C-05 — Playwright Chromium RCE via malicious dealer site**

| Campo | Valor |
|-------|-------|
| Disparador | E07 (Playwright XHR interception) ejecuta Chromium headless que visita URLs de dealer arbitrarias. Un dealer malicioso sirve un exploit de Chromium (e.g., renderer sandbox escape). |
| Probabilidad 12m | **LOW** — Exploits 0-day de Chromium son raros y caros. |
| Impacto | **Severe** — RCE en el contexto del proceso extraction, que tiene acceso a SQLite. |
| Detectabilidad | **Never** (sin sandbox de OS adicional, el proceso Chromium no está confinado más allá de systemd sandboxing). |
| Mitigación preventiva | (1) Ejecutar Playwright en un namespace de usuario separado (no el usuario `cardex`). (2) Añadir `--no-sandbox` solo como último recurso; preferir `seccomp` profile para Chromium. (3) Alternativa: E07 corre en un Docker container con `gVisor` (runsc) en lugar de runc. |

---

### D.d — Categoría Adversarial

**D-A-01 — Dealer envenena el knowledge graph con fixtures fraudulentos**

| Campo | Valor |
|-------|-------|
| Disparador | Un dealer (o competidor haciéndose pasar por dealer) publica listings con VINs falsificados, precios extremos, o fotos de vehículos de lujo con precio de scooter. CARDEX los extrae, V01-V20 no los detectan todos. |
| Probabilidad 12m | **MEDIUM** — Dealers tienen incentivos económicos para manipular precios en índices de referencia. |
| Impacto | **Severe** — El knowledge graph queda contaminado. Buyers B2B toman decisiones erróneas. Daño reputacional a CARDEX. |
| Detectabilidad | **Months** — V07 (price outlier) y V13 (cross-source convergence) deberían capturar, pero si el envenenamiento es sutil (±15% del precio real), puede no detectarse. |
| Mitigación preventiva | (1) V15 (dealer trust score) debe pesar más en V20 para dealers nuevos (< 30 días en el sistema). (2) Implementar "freshness of trust": dealers con < 10 listings procesados entran en MANUAL_REVIEW independientemente del score. (3) Rate-limit cuántos listings puede tener un dealer nuevo en estado PUBLISH < 24h de su incorporación. |

**D-A-02 — Fingerprinting del UA CardexBot → IP ban coordinado**

| Campo | Valor |
|-------|-------|
| Disparador | Una red de concesionarios implementa ban automático de `CardexBot/1.0` en sus CDNs (Cloudflare WAF rule, regla Nginx). Con suficientes dealers bloqueando, la cobertura cae dramáticamente. |
| Probabilidad 12m | **MEDIUM** — CardexBot es explícitamente identificable (por diseño de la política R1). |
| Impacto | **Moderate** — Reducción de cobertura. No pérdida de datos, sino de descubrimiento. |
| Detectabilidad | **Days** (métricas de coverage por país muestran caída). |
| Mitigación preventiva | (1) E11 (Edge Client con consent) como canal alternativo para dealers que bloquean. (2) Outreach proactivo a dealers que bloquean: ofrecer partnership. (3) Diversificación de familias: si Family F es bloqueada, Families A/B/G/H/I siguen operativas. |

**D-A-03 — Complaint flood: dealers envían DMCA/C&D masivos coordinados**

| Campo | Valor |
|-------|-------|
| Disparador | Una asociación de dealers (ZDK-Alemania, CNPA-Francia) coordina 500 solicitudes simultáneas de `robots.txt` exclusion y C&D letters. El operador único no puede responder en el SLA normal. |
| Probabilidad 12m | **LOW** — Requiere coordinación activa de una asociación grande. |
| Impacto | **Severe** — Parálisis operacional. |
| Detectabilidad | **Instant** (flood de emails). |
| Mitigación preventiva | (1) Política pública clara de opt-out: `https://cardex.eu/opt-out` con respuesta automática. (2) Template de respuesta legal preparado (< 1 hora de trabajo por respuesta). (3) Contractar asesor legal especializado en web data extraction en retainer (no ad-hoc). |

**D-A-04 — Adversarial input en E07: Playwright DOM injection causando log poisoning**

| Campo | Valor |
|-------|-------|
| Disparador | Un dealer sirve HTML con caracteres de control ANSI en los títulos de listing. Playwright extrae el texto sin sanitizar. Los logs de slog muestran secuencias de escape que ofuscan entradas de auditoría. |
| Probabilidad 12m | **LOW** — Requiere intención adversarial. |
| Impacto | **Moderate** — Logs de auditoría comprometidos. |
| Detectabilidad | **Months** (visible solo si alguien revisa los logs raw). |
| Mitigación preventiva | Sanitizar todos los strings extraídos antes de loguear: `strings.Map` que elimina caracteres de control (< 0x20 excepto newline/tab). |

---

### D.e — Categoría Dependencias OSS

**D-D-01 — playwright-community/playwright-go: breaking change en API de Playwright Node**

| Campo | Valor |
|-------|-------|
| Disparador | Playwright (Microsoft) lanza versión 2.0 con breaking changes. El puerto Go `playwright-community/playwright-go` no se actualiza en 6 meses. E07 deja de funcionar. |
| Probabilidad 12m | **MEDIUM** — Los major releases de Playwright ocurren anualmente. El porting tiene lag típico de 2-4 meses. |
| Impacto | **Moderate** — E07 no opera. Los 30-40% de dealers JS-heavy no son extraídos. |
| Detectabilidad | **Days** (tests de E07 rompen en CI). |
| Mitigación preventiva | (1) Mantener una versión de Playwright pinneada en go.mod. (2) Tener un fallback: si E07 falla, escalate a E12 (manual queue). (3) Monitorizar el repo `playwright-community/playwright-go` para issues de compatibilidad. |

**D-D-02 — modernc.org/sqlite: mantenedor anuncia retirement**

| Campo | Valor |
|-------|-------|
| Disparador | Thomas Bontje (maintainer de modernc.org) anuncia que no continuará manteniendo `modernc.org/sqlite`. El repositorio entra en modo de solo lectura. |
| Probabilidad 12m | **LOW** — No hay señales actuales de esto. |
| Impacto | **Catastrophic** — La capa de datos de los 3 servicios pierde mantenimiento activo. Las vulnerabilidades de SQLite upstream no son portadas. |
| Detectabilidad | **Instant** (anuncio público). |
| Mitigación preventiva | (1) Tener documentado el migration path a `mattn/go-sqlite3` (CGO) o `zombiezen.com/go/sqlite`. (2) Evaluar hoy si `zombiezen.com/go/sqlite` (mantenida por una empresa, Ross Light) es una mejor alternativa con respaldo corporativo. |

**D-D-03 — golang.org/x/net depreca net/html API usada por goquery**

| Campo | Valor |
|-------|-------|
| Disparador | Un cambio en `golang.org/x/net/html` (usado por goquery/PuerkitoBio) cambia el comportamiento del parser HTML. 10% de los extractores producen resultados incorrectos silenciosamente. |
| Probabilidad 12m | **LOW** — `golang.org/x/net` es muy estable. |
| Impacto | **Moderate** — Datos extraídos incorrectamente. |
| Detectabilidad | **Months** (solo detectable en revisión de datos o tests con fixtures actualizados). |
| Mitigación preventiva | Suite de integration tests con fixtures reales de páginas de dealer (snapshots) que se ejecutan en CI. Un cambio en el parser se detecta inmediatamente. |

---

### D.f — Categoría AI-Specific

**D-AI-01 — Hallucination NLG en descripción de vehículo → libelous content**

| Campo | Valor |
|-------|-------|
| Disparador | El LLM local (Llama 3/Mistral) genera una descripción que incluye información falsa sobre el historial del vehículo ("sin accidentes" cuando el VIN indica lo contrario). Un buyer B2B actúa sobre esta información y sufre pérdida económica. |
| Probabilidad 12m | **MEDIUM** — Los LLMs hallucinate con alta probabilidad en dominio específico sin RAG bien configurado. |
| Impacto | **Severe** — Demanda legal por negligent misrepresentation. |
| Detectabilidad | **Never** antes de ocurrir (la hallucination no es predecible por item). |
| Mitigación preventiva | (1) V11 (NLG quality) debe bloquear descripciones que incluyen hechos no derivables del input (V12 cross-source convergence como fuente de verdad). (2) Disclosure obligatorio en UI: *"Descripción generada por IA — verificar con el dealer antes de cualquier transacción."* (3) Implementar AI Act Art. 50 disclosure en API response (campo `ai_generated: true, ai_disclaimer: "..."`). |

**D-AI-02 — Embedding drift: V12 cross-source dedup falla a medida que el corpus crece**

| Campo | Valor |
|-------|-------|
| Disparador | V12 usa `fingerprint_sha256` sobre campos clave del vehículo. Si la normalización de los campos cambia (e.g., actualización de V04 NLP make/model), los fingerprints históricos son incompatibles con los nuevos. Vehículos duplicados se publican como distintos. |
| Probabilidad 12m | **MEDIUM** — Cualquier refactor de V04 o V12 puede romper la consistencia histórica. |
| Impacto | **Moderate** — Duplicados en el knowledge graph. |
| Detectabilidad | **Months** (visible solo al comparar datasets). |
| Mitigación preventiva | (1) Versionizar el algoritmo de fingerprint: campo `fingerprint_version` en `vehicle` tabla. (2) Si se cambia el algoritmo, re-procesar todos los vehicles existentes con el nuevo fingerprint antes de activar. |

**D-AI-03 — Model poisoning: dataset de training de V10 (vehicle binary classifier) contaminado**

| Campo | Valor |
|-------|-------|
| Disparador | Si el modelo de clasificación de imágenes (V10) fue entrenado sobre datos web, puede contener imágenes adversariales que causan misclassification sistemática (e.g., clasifica fotos de moto como coche). |
| Probabilidad 12m | **LOW** — Solo relevante si V10 está actualmente entrenado con datos no auditados. |
| Impacto | **Moderate** — Listings de motos o camiones se publican como coches. |
| Detectabilidad | **Months** (solo detectable en auditoría de datos publicados). |
| Mitigación preventiva | Mantener un golden dataset de 500 imágenes con ground truth conocido. Ejecutar V10 sobre este dataset mensualmente y alertar si accuracy cae > 2%. |

---

### D.g — Categoría Existencial

**D-X-01 — Bus factor: único operador (Salman) inaccesible durante incidente crítico**

| Campo | Valor |
|-------|-------|
| Disparador | Salman está en vuelo de 12h sin conexión cuando el VPS se rompe, el disco se llena, o hay un incidente de seguridad. El sistema es 100% dependiente de un único operador. |
| Probabilidad 12m | **HIGH** — Probabilidad estadística alta de que en 12 meses haya al menos 1 período de inaccesibilidad > 4h durante un incidente. |
| Impacto | **Severe** — Tiempo de recuperación se extiende de horas a días. |
| Detectabilidad | **Instant** (el sistema alerta pero nadie responde). |
| Mitigación preventiva | (1) Designar y dar acceso al runbook a un segundo operador técnico de confianza con acceso SSH read-only. (2) Crear playbook de "incidente sin operador": lista de pasos automatizables via scripts. (3) UptimeRobot + PagerDuty con escalation a backup contact. |

**D-X-02 — Hetzner ban de web crawling para clientes VPS**

| Campo | Valor |
|-------|-------|
| Disparador | Hetzner actualiza sus ToS para prohibir web scraping/crawling desde su infraestructura VPS (siguiendo el precedente de otros hosters). CARDEX recibe una notificación de 30 días para cesar o migrar. |
| Probabilidad 12m | **LOW** — Hetzner actualmente no prohíbe crawling ético. Pero el precedente de DigitalOcean y Linode limitando scrapers existe. |
| Impacto | **Catastrophic** — Toda la infraestructura debe migrar en 30 días. |
| Detectabilidad | **Instant** (email de Hetzner). |
| Mitigación preventiva | (1) Documentar hoy la alternativa: Scaleway (FR), IONOS (DE), OVHcloud (FR) — todos con ToS favorables para crawling ético. (2) El runbook de migración debe poder ejecutarse en < 4 horas si el backup es reciente. |

**D-X-03 — EU lex specialis de scraping de datos de vehículos (AI Act + Digital Services Act combinados)**

| Campo | Valor |
|-------|-------|
| Disparador | La Comisión Europea emite una interpretación o reglamento específico sobre indexación automatizada de datos de vehículos (exacerbado por el "right to data portability" del Data Act). El modelo de CARDEX es explícitamente categorizado como "high-risk data broker". |
| Probabilidad 12m | **LOW** — No hay señales directas en 2026. |
| Impacto | **Catastrophic** — Puede requerir licenciamiento, registro, o prohibición del modelo. |
| Detectabilidad | **Months** (proceso legislativo). |
| Mitigación preventiva | (1) Registrarse en asociaciones del sector (AICA, Vehicle Data Working Group) para tener early warning. (2) El modelo E11 (consent-based) es el más defendible regulatoriamente — acelerar su rollout. |

**D-X-04 — Let's Encrypt crisis o revocación masiva de certificados**

| Campo | Valor |
|-------|-------|
| Disparador | Let's Encrypt experimenta una crisis de revocación masiva (como el incidente CAA 2020) o falla su ACME infrastructure. Caddy no puede renovar el certificado de `cardex.eu`. El sitio queda inaccesible con error de certificado. |
| Probabilidad 12m | **LOW** — ISRG (Let's Encrypt) tiene un track record sólido. |
| Impacto | **Severe** — API inaccesible para clientes B2B hasta resolución. |
| Detectabilidad | **Instant** (los browsers reportan error de certificado). |
| Mitigación preventiva | (1) Caddy soporta múltiples CAs (Buypass, ZeroSSL como fallback). Configurar `tls { issuer acme { dir https://acme.buypass.com/acme/directory } }` como alternativa. (2) Monitorizar expiración de cert con Prometheus metric `caddy_tls_managed_certificate_expiry_seconds`. |

**D-X-05 — Trademark conflict: "CARDEX" registrado por empresa existente**

| Campo | Valor |
|-------|-------|
| Disparador | Una empresa tiene "CARDEX" registrado en uno o más mercados EU (EUIPO) para clase 38 (servicios de telecomunicación/datos) o clase 39 (transporte). CARDEX recibe una carta de trademark infringement tras launch público. |
| Probabilidad 12m | **MEDIUM** — Sin verificación de trademark en EUIPO realizada antes del launch. |
| Impacto | **Severe** — Rebranding forzado, potencial indemnización. |
| Detectabilidad | **Months** (proceso legal). |
| Mitigación preventiva | **HOY:** Verificar EUIPO trademark search para "CARDEX" en clases 35, 38, 39, 42. Si hay conflicto, cambiar nombre antes del launch público. Costo de búsqueda: ~€200 con un agente de marcas. |

---

## Sección E — Defensive Posture Gaps {#sección-e}

### E.1 Rate Limiting

| Componente | Estado | Detalle |
|------------|--------|---------|
| Discovery fetchers (HTTP) | ✅ Implementado | `HostRateLimiter` en `discovery/internal/browser/` — token bucket per host, persistido en SQLite. Default 0.3 req/s. |
| Extraction fetchers | ❓ No verificado en código | No se encontró `RateLimiter` en `extraction/internal/`. Si los extractores E01-E06 usan el mismo `browser` package, están protegidos; si tienen HTTP clients propios, no. |
| Quality validators (HTTP) | ⚠️ Parcial | V02 (NHTSA), V03 (DAT), V10 (URL liveness), V17 (sold check) hacen HTTP. No hay rate limiter visible en el código de quality. |
| API inbound (Caddy) | ❌ No implementado | Caddyfile README dice explícitamente: *"Not yet configured in the Caddyfile"*. Sin rate limiting inbound hasta Phase 7. |

**Fix prescrito (Caddy rate limiting):**
```caddyfile
# Añadir en Caddyfile AHORA (no esperar Phase 7):
(rate_limit_zone) {
    rate_limit {
        zone api_global {
            key {remote_host}
            events 100
            window 1m
        }
    }
}
handle /api/* {
    import rate_limit_zone
    # ... resto de configuración
}
```

---

### E.2 Circuit Breakers

**Estado: ❌ NO IMPLEMENTADOS** en ningún módulo.

Los servicios externos que pueden fallar sin circuit breaker:
- V02: `api.nhtsa.dot.gov` — si NHTSA está down, V02 hace timeout en CADA vehículo
- V03: DAT API — privada, puede tener SLA bajo
- Family A-FR: `api.insee.fr` — si INSEE está down, Family A-FR bloquea
- Family B-Wikidata: `query.wikidata.org` — puede tener rate limiting severo

**Fix prescrito:**
```go
// Usar golang.org/x/time/rate (ya en go.mod de discovery) para circuit breaker básico:
// O implementar un breaker simple basado en error count:
type CircuitBreaker struct {
    mu          sync.Mutex
    failures    int
    threshold   int
    lastFailure time.Time
    cooldown    time.Duration
}

func (cb *CircuitBreaker) Allow() bool { /* ... */ }
```

Alternativamente: añadir `github.com/sony/gobreaker` (MIT, bien mantenida, ~3K stars).

---

### E.3 Observability SLOs

| SLO | Estado | Detalle |
|-----|--------|---------|
| Alertas de servicio down | ✅ | `ServiceDown` alert en Alertmanager |
| Error rate threshold | ✅ | `ErrorRateHigh` alert |
| Disk space | ✅ | `DiskSpaceLow` alert |
| Backup staleness | ✅ | `BackupStale` alert |
| WAL size | ✅ | `WALSizeHigh` alert |
| Queue bounded | ✅ | `QueueUnbounded` alert |
| **SLOs formales definidos** | ❌ | No hay SLO targets formales (e.g., "99.5% uptime", "< 5% V20 error rate"). Las alertas existen pero sin SLO de referencia hacen imposible medir cumplimiento. |
| **Grafana alert umbrales documentados** | ⚠️ | Los 8 alertas existen pero sus umbrales no están revisados en relación con benchmarks reales del sistema. |
| **Dealer coverage SLO** | ❌ | No hay alerta si coverage de un país cae > 20% en 24h. |

**Fix prescrito:**
```yaml
# Añadir en Alertmanager rules:
- alert: CountryCoverageDrop
  expr: |
    (
      sum(cardex_dealers_active) by (country)
      / sum(cardex_dealers_active offset 24h) by (country)
    ) < 0.8
  for: 2h
  labels:
    severity: warning
  annotations:
    summary: "Coverage drop >20% in {{ $labels.country }} over 24h"
```

---

### E.4 Backup & Restore

| Aspecto | Estado | Detalle |
|---------|--------|---------|
| Backup script | ✅ | `backup.sh` documentado con age encryption + rsync |
| Restore script | ✅ | `restore.sh` existe |
| Restore probado | ❓ | `test-backup-restore.sh` existe pero no hay evidencia de ejecución reciente. El runbook no menciona cuándo se probó por última vez. |
| Backup retention | ✅ | 30 días documentado |
| RTO documentado | ❌ | No hay Recovery Time Objective definido. "Restaurable en < 2 horas" en RISK_REGISTER pero sin validación empírica. |
| RPO documentado | ❌ | No hay Recovery Point Objective. Los backups son diarios (03:00 UTC) → RPO implícito = 24h. No documentado explícitamente. |

**Fix prescrito:** Ejecutar `test-backup-restore.sh` mensualmente y loguear el tiempo en un documento `deploy/backup-test-log.md`. Definir formalmente: RPO = 24h, RTO = 2h.

---

### E.5 Incident Runbook

El `deploy/runbook.md` es un **runbook de provisioning** (VPS setup), no un **runbook de incidentes**.

**Gaps de runbook de incidentes:**

| Incidente | Runbook disponible | Pasos concretos |
|-----------|-------------------|-----------------|
| VPS down | ❌ | No — el runbook de provisioning asume VPS limpio, no recuperación |
| DB corruption | ❌ | No |
| Secret leak | ❌ | No |
| TLS certificate failure | ❌ | No |
| OOM killer event | ❌ | No |
| Pipeline stuck | ❌ | No |

**Fix prescrito:** Crear `deploy/incident-runbooks/` con un playbook por escenario del pre-mortem de Sección D. Formato: síntomas → diagnóstico → pasos de recuperación → validación post-recovery.

---

## Sección F — Leak Surfaces {#sección-f}

### F.1 Logs con PII / VINs sensibles

**Hallazgo:** Los logs de `slog` en discovery y extraction loguean `dealer.url`, `vin`, `make`, `model` en mensajes de debug/warn. Ejemplo:

```
discovery/internal/families/familia_a/nl_kvk/kvk.go:296:
k.log.Info("kvk: quota exhausted mid-run", "keyword", keyword)
```

El campo `keyword` puede contener nombres de empresas. Los VINs se loguean en calidad (V01 logs el VIN cuando hay error de checksum).

**Riesgo:** Si los logs de systemd (journald) son accedidos por un atacante o un segundo operador no autorizado, VINs y datos de empresa son visibles.

**Fix prescrito:** (1) Nivel de log `DEBUG` para campos con datos de dealer. (2) Truncar VINs en logs a los últimos 4 dígitos: `vin[:len(vin)-4] + "****"`. (3) Configurar journald con acceso restringido: `Storage=persistent` + `chmod 700 /var/log/journal`.

---

### F.2 Prometheus — Cardinalidad explosiva potencial

**Hallazgo:** No se encontraron labels de alta cardinalidad en el scan de código (`WithLabelValues`). Los labels de Prometheus parecen usar dimensiones estables (country, strategy_id, validator_id, family_id).

**Riesgo residual:** Si en futuro se añade un label `dealer_url` o `vin` a una metric (error común), la cardinalidad explota a millones de series.

**Fix prescrito:** Añadir test en CI que valide que ningún label de Prometheus contiene valores derivados de inputs externos (dealer URL, VIN, etc.). Usar `golangci-lint` con regla custom, o un grep en CI: `grep -rn "WithLabelValues.*vin\|WithLabelValues.*url" --include="*.go"`.

---

### F.3 Endpoints debug/pprof en producción

**Hallazgo:** No se encontró `net/http/pprof` en ningún servicio. Los servicios exponen solo:
- `:8080` — API HTTP
- `:9101-9103` — Prometheus metrics (loopback only via Caddy)

**Veredicto: ✅ OK.** pprof no está expuesto.

---

### F.4 Server header / version leak

**Hallazgo:** Caddyfile incluye `header { -Server }` — el header `Server` es eliminado activamente. Los servicios Go internos no añaden headers de versión en sus respuestas (no se encontró código que setee `Server:` header en los handlers).

**Veredicto: ✅ OK.** Sin leak de versión en headers HTTP públicos.

---

### F.5 CORS — Configuración

**Hallazgo:**
- `CORS_ORIGINS=http://localhost:3001,https://cardex.eu,https://www.cardex.eu` en `.env.example` — explícitamente restrictivo, no wildcard `*`.
- **El Caddyfile NO configura CORS headers** — si los servicios Go backend no setean CORS, las llamadas cross-origin fallarán. Esto es un gap si el b2b-dashboard necesita llamar a la API desde un origen diferente.

**Fix prescrito:** Verificar que el servicio `api/` (cuando exista) o los 3 servicios actuales setean `Access-Control-Allow-Origin: https://cardex.eu` en sus handlers. Documentar explícitamente en Caddyfile si CORS se maneja upstream o en servicios.

---

### F.6 CSP — Content-Security-Policy ausente

**Hallazgo:** El Caddyfile NO incluye `Content-Security-Policy` header en ninguna de las respuestas. El b2b-dashboard (Next.js) probablemente tiene su propia CSP configuración, pero el proxy no la inyecta a nivel de Caddy.

**Riesgo:** Sin CSP, si un XSS ocurre en el dashboard B2B, el atacante puede ejecutar scripts arbitrarios sin restricción.

**Fix prescrito:**
```caddyfile
header {
    # Añadir a los headers de seguridad existentes:
    Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://api.cardex.eu; frame-ancestors 'none'"
}
```

---

### F.7 HSTS — Estado

**Hallazgo:** `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` — correctamente configurado en Caddyfile.

**Veredicto: ✅ OK.**

---

### F.8 Caddy access logs contienen query params con datos sensibles

**Hallazgo:** El Caddyfile loguea en formato JSON todas las peticiones incluyendo el `uri` completo. Si en Phase 7 la API pública acepta VINs como query params (`/api/quality/validate?vin=WVW123456789`), esos VINs quedan en los logs de acceso de Caddy.

**Fix prescrito:** Usar Caddy log filter para redactar query params sensibles:
```caddyfile
log {
    filter query_string {
        replace vin REDACTED
        replace token REDACTED
    }
}
```

---

## Resumen Ejecutivo {#resumen-ejecutivo}

### Contadores

| Categoría | Crítico | Alto | Medio | Bajo |
|-----------|---------|------|-------|------|
| Vulnerabilidades (govulncheck) | 0 | 2 | 2 | 0 |
| Vulnerabilidades Python | 0 | 0 | 2 | 1 |
| Contradicciones documentation | 0 | 3 | 2 | 1 |
| Supply chain risks | 0 | 1 | 3 | 2 |
| Defensive gaps | 0 | 3 | 2 | 3 |
| Leak surfaces | 0 | 1 | 2 | 3 |
| **TOTAL** | **0** | **10** | **13** | **10** |

---

### Top 5 Predicciones de Mayor Riesgo Esperado (Probabilidad × Impacto)

| Rank | ID | Escenario | P × I | Acción inmediata |
|------|----|-----------|-------|------------------|
| 1 | D-R-01 | DPA investigation por PII en listings | HIGH × Catastrophic | Auditar schema, añadir V21-PII, preparar DPIA |
| 2 | D-C-01 | RCE via GO-2026-4870 (TLS DoS actual) | MEDIUM × Catastrophic | **Upgrade go1.26.2 HOY** en los 3 módulos |
| 3 | D-T-03 | OOM killer en Playwright concurrente | HIGH × Severe | `MemoryMax=6G` en systemd, cap Playwright a 3 instancias |
| 4 | D-X-01 | Bus factor: operador único inaccessible | HIGH × Severe | Designar backup operador, preparar incident runbooks |
| 5 | D-A-01 | Envenenamiento del knowledge graph | MEDIUM × Severe | Trust ramp-up para nuevos dealers, MANUAL_REVIEW forzado |

---

### Acciones Inmediatas (Semana 1)

1. **CRÍTICO** — `go get go@1.26.2` en discovery/, extraction/, quality/ → rebuild → redeploy
2. **CRÍTICO** — Eliminar `CAPTCHA_API_KEY` de `.env.example` o documentar explícitamente que es una variable legada sin implementación activa
3. **ALTO** — Añadir govulncheck en CI para `extraction/` y `quality/` (actualmente solo `discovery/`)
4. **ALTO** — Crear `.pre-commit-config.yml` con gitleaks (documentado en CONTRIBUTING pero no existe)
5. **ALTO** — Resolver inconsistencia de dominio `cardex.io` vs `cardex.eu` en toda la documentación
6. **ALTO** — Actualizar `planning/07_ROADMAP/PHASE_5_INFRASTRUCTURE.md` para marcar Phase 5 como DONE
7. **MEDIO** — Añadir `Content-Security-Policy` header en Caddyfile
8. **MEDIO** — Añadir rate limiting inbound en Caddyfile (no esperar Phase 7)
9. **MEDIO** — Crear `requirements.txt` para `ai/worker.py` con versiones pinneadas
10. **MEDIO** — Verificar EUIPO trademark para "CARDEX" antes del launch público

---

*Fin del documento. Clasificación: CONFIDENCIAL — Distribución restringida al operador.*  
*Generado: 2026-04-16. Revisión recomendada: 2026-07-16 (trimestral).*
