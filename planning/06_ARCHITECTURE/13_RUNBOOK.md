# 13 — Runbook Operacional CARDEX
**Estado:** ACTIVO  
**Bus factor:** 1 (operador único: Salman)  
**Última revisión:** 2026-04-14  
**Próxima revisión obligatoria:** antes del lanzamiento público (Phase 7)

---

## 1. Secrets Management

### Almacenamiento
- **Herramienta:** KeePassXC (open-source, zero-cloud, AES-256 + ChaCha20)
- **Base de datos:** `cardex-secrets.kdbx` — una sola base de datos para todos los secretos del proyecto
- **Master password:** mínimo 20 caracteres, mezcla de símbolos, generado por KeePassXC password generator
- **Ubicación primaria:** solo en máquina de trabajo del operador (no cloud sync)

### Backup offline de secrets
1. Exportar `cardex-secrets.kdbx` cifrado con `gpg --symmetric --cipher-algo AES256`
2. Copiar a USB cifrado (hardware encryption preferible; al menos VeraCrypt container si no)
3. USB en custodia física separada — persona de confianza designada por el operador
4. Instrucciones de acceso en sobre cerrado sellado junto al USB: URL del repositorio, procedimiento de desencriptado, contacto de emergencia

### Secretos que DEBEN estar en KeePassXC
| Secreto | Uso | Rotación recomendada |
|---------|-----|---------------------|
| SSH private key (Ed25519) | Acceso VPS | Anual o ante sospecha de compromiso |
| INSEE_TOKEN | Family A FR | Semestral |
| KVK_API_KEY | Family A NL | Semestral |
| KBO_USER / KBO_PASS | Family A BE | Semestral |
| Hetzner API key | Gestión VPS | Solo si se automatiza infra |
| Hetzner Storage Box credentials | Backup | Anual |
| GPG passphrase (backup) | Desencriptado USB | En papel en sobre sellado |
| Forgejo admin token | CI/CD | Semestral |
| healthchecks.io ping URL | Dead-man switch | Si se cambia de cuenta |

### Rotación de credentials
- Antes de rotar: hacer backup del KeePass con la credential antigua
- Actualizar en KeePass
- Actualizar en VPS: `systemctl edit discovery-service` o archivo `.env` correspondiente
- Verificar que el servicio arranca: `systemctl status discovery-service`
- Invalidar la credential antigua en el proveedor

---

## 2. Dead-Man Switch

### Propósito
Si el operador es incapaz de operar (enfermedad, accidente, otro) durante >48h, el sistema alerta automáticamente a un contacto de emergencia para que pueda tomar acción (pausar el servicio, contactar a un backup operator, etc.).

### Implementación: healthchecks.io (free tier)

**En VPS — systemd timer:**

```ini
# /etc/systemd/system/cardex-heartbeat.service
[Unit]
Description=CARDEX dead-man heartbeat ping
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/curl -fsS --retry 3 https://hc-ping.com/XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
```

```ini
# /etc/systemd/system/cardex-heartbeat.timer
[Unit]
Description=CARDEX heartbeat — cada 24h

[Timer]
OnBootSec=5min
OnUnitActiveSec=24h
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl enable cardex-heartbeat.timer
systemctl start cardex-heartbeat.timer
```

**Configuración healthchecks.io:**
- Grace period: 48h (si no se recibe ping en 48h → alerta)
- Notificación: email al operador + email a contacto de emergencia
- URL del ping: almacenada en KeePassXC bajo "CARDEX / dead-man-switch / ping URL"

**Contacto de emergencia:**
- Persona designada por el operador (nombre + email + teléfono en sobre sellado junto al USB de backup)
- Instrucciones en el sobre: "Si recibes este email de alerta, contacta a [nombre del operador] inmediatamente. Si no es posible en 24h, sigue las instrucciones de EMERGENCY_RECOVERY.md en el repositorio."

---

## 3. Disaster Recovery

### Backup automatizado

```bash
# /etc/systemd/system/cardex-backup.service
[Unit]
Description=CARDEX daily backup to Hetzner Storage Box
After=network.target

[Service]
Type=oneshot
User=cardex
ExecStart=/opt/cardex/scripts/backup.sh
```

```bash
# /opt/cardex/scripts/backup.sh
#!/bin/bash
set -euo pipefail

BACKUP_DATE=$(date +%Y-%m-%d)
LOCAL_DB="/data/discovery.db"
STORAGE_BOX="u123456@u123456.your-storagebox.de"
REMOTE_DIR="/cardex-backups"

# 1. WAL checkpoint antes del backup
sqlite3 "$LOCAL_DB" "PRAGMA wal_checkpoint(TRUNCATE);"

# 2. Crear snapshot cifrado con age
age -r "$(cat /opt/cardex/backup_pubkey.txt)" \
    -o "/tmp/discovery-${BACKUP_DATE}.db.age" \
    "$LOCAL_DB"

# 3. rsync a Storage Box
rsync -az --delete \
    "/tmp/discovery-${BACKUP_DATE}.db.age" \
    "${STORAGE_BOX}:${REMOTE_DIR}/"

# 4. Limpiar tmp
rm -f "/tmp/discovery-${BACKUP_DATE}.db.age"

# 5. Mantener últimos 30 días en Storage Box (limpiar más antiguos)
ssh "$STORAGE_BOX" "find ${REMOTE_DIR}/ -name '*.db.age' -mtime +30 -delete"

echo "Backup completado: discovery-${BACKUP_DATE}.db.age"
```

**Frecuencia:** diario (systemd timer similar al heartbeat, `OnCalendar=*-*-* 03:00:00`)  
**Retención:** 30 días rolling  
**Coste:** ~€3.20/mes para 1 TB Hetzner Storage Box (dentro del presupuesto operacional)

### Restore desde cero — Procedimiento paso a paso

```bash
# PASO 1: Provisionar nuevo VPS Hetzner CX41
# - Crear desde Hetzner Cloud Console
# - SSH key: la que está en KeePassXC
# - OS: Debian 12 minimal

# PASO 2: Instalar dependencias base
apt-get update && apt-get install -y git curl rsync age sqlite3

# PASO 3: Clonar repositorio
git clone git@forgejo.cardex.eu:cardex/cardex.git /opt/cardex

# PASO 4: Compilar el servicio
cd /opt/cardex/discovery && GOWORK=off go build -o /usr/local/bin/discovery-service ./cmd/discovery-service/

# PASO 5: Recuperar backup más reciente desde Storage Box
STORAGE_BOX="u123456@u123456.your-storagebox.de"
LATEST=$(ssh "$STORAGE_BOX" "ls /cardex-backups/*.db.age | sort | tail -1")
rsync "${STORAGE_BOX}:${LATEST}" /tmp/

# PASO 6: Desencriptar con age (private key del operador)
age --decrypt \
    -i ~/.age/cardex-backup.key \
    -o /data/discovery.db \
    /tmp/$(basename "$LATEST")

# PASO 7: Verificar integridad
sqlite3 /data/discovery.db "PRAGMA integrity_check;"

# PASO 8: Configurar variables de entorno
cp /opt/cardex/.env.example /etc/cardex.env
# Editar /etc/cardex.env con credentials de KeePassXC

# PASO 9: Instalar y arrancar servicios systemd
systemctl daemon-reload
systemctl enable --now discovery-service
systemctl enable --now cardex-heartbeat.timer
systemctl enable --now cardex-backup.timer

# PASO 10: Verificar
systemctl status discovery-service
curl http://localhost:9090/healthz
```

**RTO (Recovery Time Objective):** <4 horas desde un operador con acceso a KeePassXC  
**RPO (Recovery Point Objective):** <24 horas (último backup diario)

---

## 4. On-Call y Bus Factor

### Bus factor actual: 1

El proyecto tiene un único operador. Este es el mayor riesgo operacional existencial.
Documentado explícitamente para evitar negación del problema.

**Acciones para reducir bus factor (no presupuestadas pero necesarias antes de Phase 7):**
1. Identificar un "Backup Operator Candidate" — persona técnica de confianza
2. Onboarding documentado: acceso al repositorio, walkthrough del sistema, acceso al VPS
3. Transferir copia del USB con backup KeePassXC
4. Simulacro de disaster recovery con backup operator

**Hasta que el bus factor se resuelva:** el dead-man switch es el único mecanismo de continuidad.

---

## 5. Incident Response

### Clasificación de incidentes

| Prioridad | Definición | SLA respuesta | Ejemplo |
|-----------|-----------|--------------|---------|
| P0 — Crítico | Sistema completamente caído; datos potencialmente comprometidos | Responder en <1h | VPS down, DB corrupta, credential leakage |
| P1 — Urgente | Degradación severa; funcionalidad principal afectada | Responder en <4h | Discovery service crasheando, metrics no disponibles |
| P2 — Normal | Degradación menor; workaround disponible | Responder en <24h | Un sub-técnica fallando, backup tardío |

### Decision tree P0

```
1. ¿Es accesible el VPS?
   NO → Contactar Hetzner soporte / provisionar VPS nuevo (ver Restore desde cero)
   SÍ → continuar

2. ¿El proceso discovery-service está corriendo?
   NO → systemctl status; revisar logs: journalctl -u discovery-service -n 100
   SÍ → continuar

3. ¿La base de datos es accesible?
   sqlite3 /data/discovery.db "PRAGMA integrity_check;"
   FAIL → Restore desde backup (ver sección 3)
   OK → continuar

4. ¿Hay credential leakage (secret en git, log expuesto)?
   SÍ → Revocar credential afectada inmediatamente; notificar si hay usuarios afectados
   → Auditar git log: git log --all -S "token_value"
   → Reemplazar con nuevo secret; commit clean

5. ¿El VPS está siendo atacado (DDoS, brute force)?
   SÍ → ufw status; fail2ban-client status
   → Bloquear IP atacante: ufw deny from X.X.X.X
   → Escalar a Hetzner DDoS protection si supera capacidad
```

### Comunicación durante P0

- **Fase 1 (pre-launch):** Solo afecta al operador. No hay usuarios externos. Resolución interna.
- **Fase 2 (post-launch):** Si un incidente afecta a datos de buyers o dealers, notificación obligatoria bajo GDPR Art. 33 (72h a la DPA) y Art. 34 (si riesgo alto para personas).

### Post-mortem

Cada P0 y P1 requiere un documento de post-mortem dentro de 48h de resolución:
- Qué ocurrió (timeline)
- Causa raíz
- Impacto
- Acciones correctivas (con owner y deadline)

Almacenar en `planning/00_AUDIT/INCIDENTS/YYYY-MM-DD_P0_descripcion.md`

---

## 6. Mantenimiento rutinario

| Tarea | Frecuencia | Procedimiento |
|-------|-----------|--------------|
| Verificar estado backup | Semanal | `ssh storagebox ls /cardex-backups/` — verificar fecha del último |
| Revisar logs discovery | Semanal | `journalctl -u discovery-service --since "7 days ago" \| grep -E "ERROR\|WARN"` |
| Verificar métricas Grafana | Semanal | Revisar dashboards: dealers_total, cycle_duration, health_check_status |
| Actualizar go.sum (security) | Mensual | `govulncheck ./...` — parchear si CVE encontrado |
| Rotar secrets sensibles | Semestral | Ver sección 1 Rotación de credentials |
| Simular restore | Anual | Levantar VPS temporal, restaurar backup, verificar integridad |
| Revisar robots.txt sources | Antes de cada sprint | Verificar que ninguna source tiene cambios en robots.txt relevantes |
