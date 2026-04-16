> **STATUS: COMPLETE** — Phase 5 infrastructure delivered in sprint 23 (2026-04-14).
> See CHANGELOG.md §[Phase 5]. This document is archived for reference.

# PHASE_5 — Infrastructure

## Identificador
- ID: P5, Nombre: Infrastructure — VPS producción + observabilidad + CI/CD
- Estado: PENDING
- Dependencias de fases previas: P4 (DONE) — puede paralelizarse parcialmente con P4
- Fecha de documentación: 2026-04-14

## Propósito y rationale

P5 convierte el sistema de un entorno de desarrollo/staging a una plataforma de producción operativa. Esto incluye el VPS de producción configurado y hardenizado, la observabilidad end-to-end (Prometheus + Grafana), los backups verificados, el CI/CD operativo (Forgejo), y el runbook aprobado.

P5 puede paralelizarse con P4: mientras P4 construye el pipeline de calidad, P5 puede configurar el VPS, instalar Docker, desplegar Prometheus+Grafana, y preparar los systemd units. Lo que no puede hacerse antes de que P4 esté completa es el "primer deploy de producción" — pero toda la preparación de infraestructura sí.

Un sistema que no puede operar 7 días seguidos sin intervención manual no está listo para producción. El criterio de P5 mide exactamente esto.

## Objetivos concretos

1. Provisionar el VPS Hetzner CX41 con Debian 12 minimal, particionado y sysctl hardening
2. Instalar y configurar todos los servicios systemd de CARDEX (discovery, extraction, quality, nlg, index, api, sse)
3. Instalar y configurar Docker Compose con SearXNG, Prometheus, Grafana, Forgejo
4. Configurar Caddy con TLS automático y todas las rutas del API
5. Configurar Hetzner Storage Box + script de backup `age`-encrypted + verificar restore
6. Configurar UFW, SSH hardening, fail2ban, unattended-upgrades según `09_SECURITY_HARDENING.md`
7. Importar todos los dashboards Grafana y activar las alerting rules de `08_OBSERVABILITY.md`
8. Activar Forgejo con el pipeline CI completo (incluido illegal-pattern scanner)
9. Ejecutar el sistema 7 días consecutivos sin intervención manual
10. Ejecutar simulacro de restore de backup completo
11. Redactar y aprobar el runbook operacional

## Entregables

| Entregable | Verificación |
|---|---|
| VPS Hetzner CX41 productivo | SSH acceso, `uname -a` muestra Debian 12 |
| systemd units activos | `systemctl is-active cardex-*` todos = active |
| Docker Compose running | `docker compose ps` todos healthy |
| Caddy TLS activo | `curl -I https://cardex.io` → 200 con HSTS header |
| Backups funcionando 7 días | `ls` en Storage Box muestra 7 archivos daily |
| Backup restore test | Documento de test firmado por operador |
| Prometheus + Grafana | 6 dashboards importados, datos fluyendo |
| Forgejo CI pipeline | PR test exitoso; illegal-pattern scan bloqueante verificado |
| Runbook operacional | Documento en `docs/runbook.md`, aprobado por operador |
| Security checklist | `09_SECURITY_HARDENING.md` checklist completo |

## Criterios cuantitativos de salida

### CS-5-1: Sistema corriendo 7 días consecutivos sin intervención manual

```promql
# API uptime durante los últimos 7 días
avg_over_time(up{job="cardex-api"}[7d]) >= 0.99

# Quality service uptime
avg_over_time(up{job="cardex-quality"}[7d]) >= 0.99

# Discovery service uptime
avg_over_time(up{job="cardex-discovery"}[7d]) >= 0.99
```

```sql
-- Sin entradas de intervención manual en el registro de operaciones
SELECT COUNT(*)
FROM operations_log
WHERE action = 'manual_restart'
  AND created_at > DATETIME('now', '-7 days');
-- Resultado esperado: 0
```

### CS-5-2: API p99 latency <3s en condiciones normales

```promql
histogram_quantile(0.99,
  rate(cardex_api_query_duration_seconds_bucket[1h])
) < 3.0
```

### CS-5-3: 0 fallos de backup en 7 días

```bash
# El script de backup registra su resultado en un log
grep -c "ERROR\|FAILED" /var/log/cardex/backup.log
# Resultado esperado: 0 (en los últimos 7 días)

# Storage Box contiene ≥7 backups daily
ssh -i /etc/cardex/credentials/storagebox \
  u123456@u123456.your-storagebox.de \
  "ls backups/cardex/daily/ | wc -l"
# Resultado esperado: ≥7
```

### CS-5-4: Backup restore test exitoso

```bash
# Test documentado: descargar el backup más reciente, decrypt con age, restaurar en VPS tmp
# Verificar que SQLite OLTP es legible y tiene datos coherentes
# El test es manual y produce un documento firmado — no es automatizable
# Criterio binario: documento existe en docs/backup-restore-test-YYYY-MM-DD.md
ls docs/backup-restore-test-*.md | wc -l
# Resultado esperado: ≥1
```

### CS-5-5: CI/CD pipeline operativo con illegal-pattern scan activo

```bash
# Verificar que el pipeline rechaza un PR con patrón ilegal
# Test E2E documentado en CI: crear rama test con import curl_cffi, verificar que CI falla
# Criterio binario: test E2E pasado (resultado en Forgejo visible)
```

```sql
-- Forgejo ha ejecutado ≥N pipelines en la última semana (sign of health)
-- Verificado via Forgejo API
```

### CS-5-6: Runbook aprobado

```bash
# Documento existe y tiene aprobación formal del operador
cat docs/runbook.md | grep -c "^## "
# Resultado esperado: ≥10 secciones (procedimientos de: restart, rollback, backup restore, 
# scale up, troubleshooting, legal incident, dependency failure, etc.)

grep "APPROVED BY:" docs/runbook.md
# Resultado esperado: línea con nombre y fecha del operador
```

### CS-5-7: Security checklist completado

```bash
# Verificar hardening básico
# SSH: no password auth
grep "PasswordAuthentication no" /etc/ssh/sshd_config.d/99-cardex.conf

# UFW activo
ufw status | grep "Status: active"

# fail2ban activo
systemctl is-active fail2ban

# Automatic security updates activo
systemctl is-active unattended-upgrades
```

## Métricas de progreso intra-fase

| Métrica | Expresión | Objetivo |
|---|---|---|
| Services running | `systemctl is-active cardex-*` | 7/7 active |
| Docker containers healthy | `docker compose ps` | 4/4 healthy |
| Uptime API (7d) | CS-5-1 promql | ≥99% |
| API latency p99 | CS-5-2 | <3s |
| Backup success rate | CS-5-3 | 100% (0 fallos) |
| Dashboards Grafana importados | Panel count | 6/6 |

## Actividades principales

1. **Provisionar VPS** — contratar Hetzner CX41 NBG1, instalar Debian 12 minimal, configurar sysctl, particionado /srv, swap
2. **SSH + firewall** — Ed25519 keys, UFW reglas, fail2ban jails, unattended-upgrades
3. **Instalar runtime** — Go 1.22, Docker, Docker Compose, Caddy, Playwright browsers
4. **Descargar datos** — NHTSA mirror SQLite, MaxMind GeoLite2, ONNX models, Llama 3 8B GGUF (4.5 GB), LanguageTool JAR
5. **Configurar Docker Compose** — SearXNG, Prometheus, Grafana, Forgejo
6. **Importar dashboards Grafana** — 6 dashboards de `08_OBSERVABILITY.md`
7. **Configurar alerting rules** — 9 reglas de `08_OBSERVABILITY.md`
8. **Deploy systemd units** — copiar 8 unit files, habilitar, arrancar
9. **Configurar Caddy** — Caddyfile de `07_DEPLOYMENT_TOPOLOGY.md`, verificar TLS
10. **Configurar backup** — Storage Box, script de backup, systemd timer, primer backup manual
11. **Configurar Forgejo + CI** — push código, verificar pipeline completo incluido illegal-pattern scan
12. **7 días de marcha blanca** — monitorizar dashboards, no intervenir salvo emergencia real
13. **Backup restore test** — documentar resultado
14. **Redactar runbook** — procedimientos de operación
15. **Retrospectiva** con todos los criterios CS-5-* documentados

## Dependencias externas

- P4 DONE o muy avanzada (binarios Go listos para deploy)
- Tarjeta de crédito/cuenta Hetzner activa
- Dominio registrado (cardex.io o equivalente) con DNS configurado al IP del VPS
- Let's Encrypt alcanzable desde el VPS (puerto 443 abierto)
- Clave pública age generada y almacenada offline por el operador

## Riesgos específicos de la fase

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| NLG batch consume toda la RAM durante las 7 noches de prueba, afectando uptime de API | MEDIA | ALTA | Configurar `MemoryMax=6G` en nlg.service; verificar que OOM killer no mata api.service durante ventana nocturna |
| Hetzner Storage Box SFTP lento para backups grandes (>5 GB) | BAJA | BAJA | rsync incremental — solo transfiere deltas; el primer backup completo puede tardar más, aceptable |
| Let's Encrypt rate limit (5 certificados/semana por dominio) | BAJA | ALTA | Usar staging endpoint de LE en las pruebas iniciales; solo pasar a production LE cuando el DNS es definitivo |
| Forgejo consumiendo mucha RAM (512 MB límite) | BAJA | BAJA | Forgejo con 512 MB es conservador; puede ampliarse si es necesario sin afectar otros servicios |
| Disco /srv lleno antes de completar los 7 días (descarga de modelos + datos) | BAJA | MEDIA | Calcular espacio antes: ONNX 500MB + Llama 4.5GB + NHTSA 3.5GB + MaxMind 100MB + DuckDB ≈ 10 GB inicial; mucho margen en 240 GB |

## Retrospectiva esperada

Al cerrar P5, evaluar:
- ¿Los 7 días sin intervención manual se completaron limpiamente? ¿Qué alertas se dispararon?
- ¿El backup restore test reveló algún problema (formato, compatibilidad de SQLite versiones)?
- ¿El runbook cubre todos los escenarios que el operador considera relevantes?
- ¿La distribución de RAM durante la ventana NLG fue dentro de lo esperado?
- ¿El CI/CD pipeline tardó más de lo esperado en arrancar? ¿Qué fricción hubo?
