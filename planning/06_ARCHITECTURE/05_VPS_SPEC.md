# 05 — VPS Specification

## Identificador
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Vendor Comparison

### Criterios de evaluación
1. **CPU:** ≥4 vCPU AMD/Intel moderno (NLG batch requiere ~4 vCPU × 5s por registro)
2. **RAM:** ≥16 GB (Llama 3 8B Q4_K_M requiere ~4.5 GB, más ~3-4 GB OS+servicios)
3. **Almacenamiento:** ≥200 GB NVMe SSD (NHTSA mirror 3.5 GB, Llama 4.5 GB, OLAP parquet estimado 50 GB growth)
4. **Red:** ≥10 TB/mes outbound (crawling continuo + API traffic)
5. **Ubicación:** EU (GDPR compliance, baja latencia targets DE/FR/ES)
6. **Certificación:** ISO 27001 (requisito para buyers B2B corporativos)
7. **Precio:** objetivo <€25/mes VPS base

### Tabla comparativa

| Vendor | Plan | CPU | RAM | SSD | Tráfico | Precio/mes | ISO 27001 | Nota |
|---|---|---|---|---|---|---|---|---|
| **Hetzner** | CX41 | 4 vCPU AMD EPYC | 16 GB | 240 GB NVMe | 20 TB | **€18** | ✓ | **RECOMENDADO** |
| **Hetzner** | CX51 | 8 vCPU AMD EPYC | 32 GB | 360 GB NVMe | 20 TB | €32 | ✓ | Escalado vertical S1 |
| **Hetzner** | EX44 (dedicated) | 4-Core i5-13500 | 64 GB | 2×512 GB NVMe | 20 TB | €45 | ✓ | Opción S2, bare metal |
| **Contabo** | VPS S | 6 vCPU | 16 GB | 50 GB NVMe | unlimited | €6 | ✗ | Almacenamiento insuficiente — DESCARTAR |
| **Contabo** | VPS M | 8 vCPU | 16 GB | 400 GB NVMe | unlimited | €15 | ✗ | Precio atractivo, sin ISO 27001, perf variable documentada |
| **Scaleway** | DEV1-L | 4 vCPU | 8 GB | 80 GB NVMe | 200 GB | €20 | ✓ (parcial) | RAM insuficiente (8 GB) — DESCARTAR |
| **OVH** | VPS-3 | 4 vCPU | 8 GB | 80 GB SSD | 250 GB/mo | €17 | ✓ | RAM insuficiente (8 GB) — DESCARTAR |
| **IONOS** | VPS XL | 8 vCPU | 16 GB | 240 GB SSD | unlimited | €18 | ✓ | Sin NVMe confirmado, support peor reputación |
| **DigitalOcean** | Premium AMD 4/16 | 4 vCPU | 16 GB | 200 GB NVMe | 6 TB | €72 | ✓ | Precio no competitivo — DESCARTAR |
| **AWS EC2** | t3.xlarge | 4 vCPU | 16 GB | EBS 100 GB | ~pay-per-GB | ~€150 | ✓ | OPEX variable, vendor lock-in — DESCARTAR |

### Análisis de las 2 opciones finalistas

#### Hetzner CX41 (RECOMENDADO)
- **CPU:** AMD EPYC Rome 7003, rendimiento consistente y documentado en benchmarks públicos
- **NVMe:** velocidades de escritura secuencial ~1.5 GB/s → DuckDB OLAP y SQLite WAL-intensive sin bottleneck
- **Tráfico:** 20 TB incluidos (estimado CARDEX S0: ~3-5 TB/mes) → margen holgado
- **Red:** Nürnberg DC (baja latencia a DE/AT) o Helsinki (baja latencia a Nordics)
- **ISO 27001:** certificado para todos los DCs, obligatorio para buyers corporativos B2B
- **Panel:** API Hetzner Cloud para provisionamiento, snapshots automáticos
- **Soporte:** documentación excelente, foro activo, SLA 99.9% uptime
- **Contrapartida:** sin plan gratuito de outbound masivo a terceros (crawling intensivo) — verificar terms of service. El TOS permite bots si no son abusivos. CardexBot/1.0 con rate limiting por dominio cumple.

#### Contabo VPS M (ALTERNATIVA DE EMERGENCIA)
- Precio €15/mes — ahorro €3/mes sobre Hetzner
- 8 vCPU vs 4 → ventaja en parallelismo NLG
- **Contras:** sin ISO 27001, performance históricamente variable (overcrowding documentado en benchmarks comunidad), soporte lento, ubicación DE/US
- Usar solo si Hetzner CX41 no está disponible en región objetivo

## Recomendación Final

**Hetzner CX41 — CPX41 (AMD)** en Nürnberg (NBG1) o Falkenstein (FSN1)

```
Plan:           CX41 (AMD EPYC)
vCPU:           4 dedicadas
RAM:            16 GB DDR4
Storage:        240 GB NVMe SSD
Tráfico:        20 TB/mes incluidos
Precio:         €18/mes (sin IVA)
Región:         Nürnberg NBG1 (primaria) / Helsinki HEL1 (backup)
ISO 27001:      ✓ certificado
Proveedor DNI:  Hetzner Online GmbH, Industriestr. 25, 91710 Gunzenhausen, DE
```

## Especificación del Sistema Operativo

### OS base
```
Distribución:   Debian 12 (Bookworm) stable — minimal install (no GUI, no desktop)
Kernel:         Linux 6.1 LTS (default Debian 12)
Arquitectura:   amd64
Boot:           UEFI + systemd-boot
```

### Sysctl hardening (aplicado via `/etc/sysctl.d/99-cardex.conf`)
```ini
# Network hardening
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1
net.ipv4.tcp_timestamps = 0

# Memory protection
kernel.randomize_va_space = 2
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 2

# File limits (para SQLite WAL + DuckDB concurrent handles)
fs.file-max = 200000
```

## Particionado del Disco

```
Disco total:    240 GB NVMe

/               20 GB    ext4    OS, binarios, systemd units
/var/log        20 GB    ext4    journald, logs audit, logs aplicación
/srv            196 GB   ext4    datos aplicación (ver abajo)
swap            4 GB     swap    (file, no partición separada)

Estructura /srv/:
/srv/cardex/
├── db/
│   ├── main.db          # SQLite OLTP (knowledge graph, vehicle records)
│   ├── fx.db            # FX rates cache
│   └── nhtsa.db         # NHTSA vPIC mirror (~3.5 GB)
├── olap/
│   └── vehicles.duckdb  # DuckDB OLAP + parquet files
├── models/
│   ├── onnx/            # YOLOv8n, MobileNetV3, spaCy (~500 MB)
│   └── llm/
│       └── llama3-8b-q4_k_m.gguf  # Llama 3 8B Q4_K_M (~4.5 GB)
├── data/
│   ├── geo/             # MaxMind GeoLite2 city DB (~100 MB)
│   └── equipment/       # equipment_vocabulary.yaml
├── lt/                  # LanguageTool JAR (~200 MB)
├── backups/             # rsync local antes de push a Storage Box
└── www/                 # Manual review UI (React SPA static build)
```

## Configuración del Sistema

### SSH
```
Port:                   22 (opcional mover a no-estándar)
PermitRootLogin:        no
PasswordAuthentication: no
PubkeyAuthentication:   yes
AuthorizedKeysFile:     .ssh/authorized_keys
Protocol:               2
KexAlgorithms:          curve25519-sha256,diffie-hellman-group14-sha256
Ciphers:                chacha20-poly1305@openssh.com,aes256-gcm@openssh.com
MACs:                   hmac-sha2-256-etm@openssh.com,hmac-sha2-512-etm@openssh.com
LoginGraceTime:         30s
MaxAuthTries:           3
AllowUsers:             cardex
```

### Zona horaria y locale
```bash
timedatectl set-timezone Europe/Madrid
localectl set-locale LANG=en_US.UTF-8
```

### Automatic security updates
```bash
apt install unattended-upgrades
# /etc/apt/apt.conf.d/50unattended-upgrades
# → solo security updates, no-dist-upgrade
# → reboot automático a las 04:00 CET si necesario (ventana no-NLG)
```

### systemd-journald (logs persistentes)
```ini
# /etc/systemd/journald.conf
[Journal]
Storage=persistent
Compress=yes
MaxRetentionSec=30d
MaxFileSec=1week
SystemMaxUse=5G
```

## Sistema de Backup

### Hetzner Storage Box
```
Plan:           Storage Box 1 TB — BX11
Precio:         €3/mes
Protocolo:      SFTP / SAMBA / rsync-over-SSH
Ubicación:      mismo DC que el VPS (baja latencia, tráfico interno gratuito)
Encriptación:   age (moderno, alternativa gpg) — clave pública en el VPS, clave privada offline
```

### Script de backup (`/usr/local/bin/cardex-backup.sh`)
```bash
#!/bin/bash
set -euo pipefail

BACKUP_ROOT="/srv/cardex/backups"
REMOTE="u123456@u123456.your-storagebox.de:/backups/cardex"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_ROOT}/daily_${DATE}"

# 1. Dump SQLite (checkpoint WAL antes)
sqlite3 /srv/cardex/db/main.db "PRAGMA wal_checkpoint(FULL);"
sqlite3 /srv/cardex/db/nhtsa.db "PRAGMA wal_checkpoint(FULL);"

# 2. Snapshot DuckDB (copy while service paused briefly)
systemctl stop cardex-index
cp -r /srv/cardex/olap/ "${BACKUP_DIR}/olap/"
systemctl start cardex-index

# 3. Backup SQLite files + config
cp /srv/cardex/db/*.db "${BACKUP_DIR}/db/"
cp -r /srv/cardex/data/ "${BACKUP_DIR}/data/"

# 4. Encrypt con age
tar czf - "${BACKUP_DIR}" | age -r "$(cat /etc/cardex/backup-pubkey.txt)" > "${BACKUP_DIR}.tar.gz.age"
rm -rf "${BACKUP_DIR}"

# 5. rsync diferencial a Storage Box
rsync -az --delete \
    --link-dest="${BACKUP_ROOT}/latest" \
    "${BACKUP_DIR}.tar.gz.age" \
    "${REMOTE}/daily/"

ln -snf "${BACKUP_DIR}.tar.gz.age" "${BACKUP_ROOT}/latest"
```

### Política de retención
```
Daily backups:   30 días (rotación automática)
Weekly backups:  12 semanas (domingo 02:00 CET)
Monthly backups: 12 meses (primer domingo del mes)

Tiempo estimado de restauración completa: <2 horas
RPO (Recovery Point Objective): 24 horas
RTO (Recovery Time Objective): 4 horas
```

### Monitorización externa
```
Servicio:    UptimeRobot (free tier)
Endpoint:    https://cardex.io/health
Intervalo:   5 minutos
Alerta:      email a operator en <2 minutos de downtime
```

## Coste Total Mensual (S0)

| Concepto | Vendor | Coste/mes |
|---|---|---|
| VPS CX41 (4 vCPU, 16 GB RAM, 240 GB NVMe, 20 TB tráfico) | Hetzner | €18.00 |
| Storage Box BX11 (1 TB, backups cifrados) | Hetzner | €3.00 |
| Monitorización externa (HTTPS ping, alertas email) | UptimeRobot | €0.00 (free) |
| Dominio cardex.io (amortizado mensual) | Namecheap | ~€1.25 |
| **TOTAL OPEX mensual** | | **€22.25** |

> Nota: todo el software (Go, Python, Llama, ONNX, DuckDB, SQLite, Prometheus, Grafana, Forgejo, SearXNG, Caddy, LanguageTool) es open-source sin coste de licencia. El coste real de infraestructura es €22.25/mes.
