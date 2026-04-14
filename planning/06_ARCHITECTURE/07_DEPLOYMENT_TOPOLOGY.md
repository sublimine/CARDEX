# 07 — Deployment Topology

## Identificador
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Visión general

```
Internet
    │
    ▼ :443 HTTPS (solo puerto expuesto al exterior)
┌───────────────────────────────────────────────────────────────────┐
│  Caddy (systemd)  — TLS termination + reverse proxy               │
│  Let's Encrypt automático, Mozilla modern TLS profile             │
└───────────────────────────────────────────────────────────────────┘
    │ Unix socket /run/caddy/api.sock
    ▼
┌──────────────────┐    NATS embedded    ┌──────────────────────────┐
│  api.service     │◄────────────────────│  discovery.service       │
│  :8080 loopback  │                     │  extraction.service      │
│  :8081 SSE       │                     │  quality.service         │
└──────────────────┘                     │  index.service           │
                                         └──────────────────────────┘
                                                     │
                              ┌──────────────────────┤
                              ▼                      ▼
                    /srv/cardex/db/           /srv/cardex/olap/
                    main.db (SQLite)          vehicles.duckdb
                    nhtsa.db (SQLite)         parquet files
                    fx.db (SQLite)

Docker network (172.20.0.0/24, bridge):
┌────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  SearXNG   │  │ Prometheus  │  │   Grafana   │  │   Forgejo   │
│  :8888     │  │  :9090      │  │   :3001     │  │  :3002/2222 │
└────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
  (solo acceso desde loopback — no expuesto al exterior)
```

## Systemd Units

### cardex-discovery.service

```ini
# /etc/systemd/system/cardex-discovery.service
[Unit]
Description=CARDEX Discovery Service — familias A-O
After=network-online.target cardex-nats.service
Wants=network-online.target
Requires=cardex-nats.service

[Service]
Type=simple
User=cardex
Group=cardex
WorkingDirectory=/srv/cardex
ExecStart=/usr/local/bin/cardex-discovery
Restart=on-failure
RestartSec=30s

# Recursos
MemoryMax=512M
CPUQuota=80%

# Seguridad
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/srv/cardex/db
ProtectHome=yes
SystemCallFilter=@system-service

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=cardex-discovery

# Variables de entorno (secrets via systemd-creds)
LoadCredential=db-path:/etc/cardex/credentials/db-path
LoadCredential=nats-url:/etc/cardex/credentials/nats-url
Environment=DISCOVERY_CYCLE_INTERVAL=6h
Environment=DISCOVERY_COUNTRIES=DE,FR,ES,BE,NL,CH
Environment=METRICS_PORT=9101

[Install]
WantedBy=multi-user.target
```

### cardex-extraction.service

```ini
# /etc/systemd/system/cardex-extraction.service
[Unit]
Description=CARDEX Extraction Service — E01-E12
After=network-online.target cardex-nats.service
Wants=network-online.target
Requires=cardex-nats.service

[Service]
Type=simple
User=cardex
Group=cardex
WorkingDirectory=/srv/cardex
ExecStart=/usr/local/bin/cardex-extraction
Restart=on-failure
RestartSec=30s

# Playwright requiere más memoria por Chromium
MemoryMax=1G
CPUQuota=150%

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/srv/cardex/db /tmp/cardex-playwright

StandardOutput=journal
StandardError=journal
SyslogIdentifier=cardex-extraction

Environment=PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/playwright
Environment=METRICS_PORT=9102
Environment=MAX_CONCURRENT_EXTRACTIONS=8
Environment=RATE_LIMIT_DEFAULT_RPS=0.5

[Install]
WantedBy=multi-user.target
```

### cardex-quality.service

```ini
# /etc/systemd/system/cardex-quality.service
[Unit]
Description=CARDEX Quality Pipeline — V01-V20
After=network-online.target cardex-nats.service
Wants=network-online.target
Requires=cardex-nats.service

[Service]
Type=simple
User=cardex
Group=cardex
WorkingDirectory=/srv/cardex
ExecStart=/usr/local/bin/cardex-quality
Restart=on-failure
RestartSec=15s

# ONNX models (YOLOv8n, MobileNetV3, spaCy) cargados en memoria
MemoryMax=700M
CPUQuota=200%

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/srv/cardex/db
ReadOnlyPaths=/srv/cardex/models /srv/cardex/data

StandardOutput=journal
StandardError=journal
SyslogIdentifier=cardex-quality

Environment=ONNX_MODELS_DIR=/srv/cardex/models/onnx
Environment=NHTSA_DB=/srv/cardex/db/nhtsa.db
Environment=FX_DB=/srv/cardex/db/fx.db
Environment=METRICS_PORT=9103

[Install]
WantedBy=multi-user.target
```

### cardex-nlg.service + cardex-nlg.timer (batch nocturno)

```ini
# /etc/systemd/system/cardex-nlg.service
[Unit]
Description=CARDEX NLG Batch — generación de descripciones Llama 3
After=network-online.target cardex-nats.service

[Service]
Type=oneshot
User=cardex
Group=cardex
WorkingDirectory=/srv/cardex
ExecStart=/usr/local/bin/cardex-nlg --mode=batch --max-items=1000

# Llama 3 8B Q4_K_M: 4.5 GB RAM + overhead
MemoryMax=6G
# 4 vCPU dedicados durante la ventana nocturna
CPUQuota=400%
# Timeout máximo de 5.5 horas (hasta las 06:00)
TimeoutStartSec=19800

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/srv/cardex/db
ReadOnlyPaths=/srv/cardex/models/llm

StandardOutput=journal
StandardError=journal
SyslogIdentifier=cardex-nlg
```

```ini
# /etc/systemd/system/cardex-nlg.timer
[Unit]
Description=CARDEX NLG Batch — 00:30 CET diario
Requires=cardex-nlg.service

[Timer]
OnCalendar=*-*-* 00:30:00 Europe/Madrid
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

### cardex-index.service

```ini
# /etc/systemd/system/cardex-index.service
[Unit]
Description=CARDEX Index Writer — OLTP + OLAP
After=network-online.target cardex-nats.service
Requires=cardex-nats.service

[Service]
Type=simple
User=cardex
Group=cardex
WorkingDirectory=/srv/cardex
ExecStart=/usr/local/bin/cardex-index
Restart=on-failure
RestartSec=10s

MemoryMax=300M
CPUQuota=80%

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/srv/cardex/db /srv/cardex/olap

StandardOutput=journal
StandardError=journal
SyslogIdentifier=cardex-index
Environment=METRICS_PORT=9106
Environment=TTL_HOURS=72

[Install]
WantedBy=multi-user.target
```

### cardex-api.service

```ini
# /etc/systemd/system/cardex-api.service
[Unit]
Description=CARDEX API Service — REST + SSE
After=network-online.target cardex-nats.service
Requires=cardex-nats.service

[Service]
Type=simple
User=cardex
Group=cardex
WorkingDirectory=/srv/cardex
ExecStart=/usr/local/bin/cardex-api
Restart=on-failure
RestartSec=5s

MemoryMax=400M
CPUQuota=100%

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadOnlyPaths=/srv/cardex/db /srv/cardex/olap /srv/cardex/www

# Unix socket para Caddy
RuntimeDirectory=cardex-api
ExecStartPre=/bin/mkdir -p /run/cardex-api
RuntimeDirectoryMode=0750

StandardOutput=journal
StandardError=journal
SyslogIdentifier=cardex-api

Environment=API_SOCKET=/run/cardex-api/api.sock
Environment=SSE_PORT=8081
Environment=METRICS_PORT=9105
Environment=DUCKDB_PATH=/srv/cardex/olap/vehicles.duckdb
LoadCredential=api-key-salt:/etc/cardex/credentials/api-key-salt

[Install]
WantedBy=multi-user.target
```

### FX rate updater timer

```ini
# /etc/systemd/system/cardex-fx-updater.timer
[Timer]
OnCalendar=*-*-* 17:00:00 Europe/Madrid  # después de las 16:00 CET ECB update
Persistent=true

# /etc/systemd/system/cardex-fx-updater.service
[Service]
Type=oneshot
User=cardex
ExecStart=/usr/local/bin/cardex-fx-updater --source=ecb
TimeoutStartSec=120
```

## Docker Compose (servicios auxiliares)

```yaml
# /srv/cardex/docker/docker-compose.yml
version: '3.8'

networks:
  cardex-aux:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/24

services:
  searxng:
    image: searxng/searxng:latest
    container_name: cardex-searxng
    restart: unless-stopped
    networks:
      - cardex-aux
    ports:
      - "127.0.0.1:8888:8080"  # solo loopback
    volumes:
      - /srv/cardex/docker/searxng:/etc/searxng:ro
    environment:
      - SEARXNG_SECRET=changeme_random_32chars
    mem_limit: 512m

  prometheus:
    image: prom/prometheus:latest
    container_name: cardex-prometheus
    restart: unless-stopped
    networks:
      - cardex-aux
    ports:
      - "127.0.0.1:9090:9090"  # solo loopback
    volumes:
      - /srv/cardex/docker/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=90d'
      - '--storage.tsdb.path=/prometheus'
    mem_limit: 512m

  grafana:
    image: grafana/grafana:latest
    container_name: cardex-grafana
    restart: unless-stopped
    networks:
      - cardex-aux
    ports:
      - "127.0.0.1:3001:3000"  # solo loopback
    volumes:
      - grafana-data:/var/lib/grafana
      - /srv/cardex/docker/grafana/provisioning:/etc/grafana/provisioning:ro
    environment:
      - GF_SECURITY_ADMIN_PASSWORD_FILE=/run/secrets/grafana_admin_password
      - GF_SERVER_ROOT_URL=http://localhost:3001
      - GF_ANALYTICS_REPORTING_ENABLED=false
    mem_limit: 256m

  forgejo:
    image: codeberg.org/forgejo/forgejo:latest
    container_name: cardex-forgejo
    restart: unless-stopped
    networks:
      - cardex-aux
    ports:
      - "127.0.0.1:3002:3000"  # solo loopback
      - "127.0.0.1:2222:22"    # SSH para git push
    volumes:
      - forgejo-data:/data
      - /etc/timezone:/etc/timezone:ro
    environment:
      - USER_UID=1000
      - USER_GID=1000
    mem_limit: 512m

volumes:
  prometheus-data:
  grafana-data:
  forgejo-data:
```

## Caddy — Reverse Proxy + TLS

```caddyfile
# /etc/caddy/Caddyfile
cardex.io, www.cardex.io {
    # TLS automático Let's Encrypt
    tls {
        protocols tls1.3
        curves x25519
        ciphers TLS_CHACHA20_POLY1305_SHA256 TLS_AES_256_GCM_SHA384
    }

    # Headers de seguridad
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        X-XSS-Protection "1; mode=block"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server
    }

    # API endpoints → api service via Unix socket
    handle /api/* {
        reverse_proxy unix//run/cardex-api/api.sock
    }

    # SSE endpoint → sse gateway (keepalive largo)
    handle /events* {
        reverse_proxy localhost:8081 {
            transport http {
                keepalive off
                response_header_timeout 0
            }
        }
    }

    # Edge client ingestion
    handle /edge/* {
        reverse_proxy unix//run/cardex-api/api.sock {
            transport http {
                tls_client_auth /etc/cardex/tls/edge-ca.crt
            }
        }
    }

    # Manual review UI (solo desde loopback / SSH tunnel)
    handle /review/* {
        @local {
            remote_ip 127.0.0.1
        }
        handle @local {
            root * /srv/cardex/www
            file_server
        }
        handle {
            respond 403
        }
    }

    # Health check (para UptimeRobot)
    handle /health {
        respond "OK" 200
    }

    # Rate limiting global por IP
    rate_limit {
        zone api_global {
            key {remote_host}
            events 100
            window 1m
        }
    }
}
```

## Secrets Management

### Opción implementada: systemd-creds + age (fase S0)

```bash
# Crear credencial cifrada para systemd
echo "postgresql://..." | systemd-creds encrypt --name=db-path -p - \
    /etc/cardex/credentials/db-path

# En el .service unit:
LoadCredential=db-path:/etc/cardex/credentials/db-path
# Acceso en Go via os.ReadFile("/run/credentials/cardex-service/db-path")
```

### Secrets almacenados
```
/etc/cardex/credentials/
├── db-path             # path al SQLite OLTP
├── nats-url            # nats://localhost:4222 (local, baja sensibilidad)
├── api-key-salt        # salt para HMAC API keys B2B
├── backup-pubkey.txt   # public key age para backup encryption
└── edge-mtls/          # certificados TLS para Edge Client E11
    ├── ca.crt
    ├── server.crt
    └── server.key
```

### Rotación de secrets (90 días)
```
API key salt:      rotación programada cada 90 días (systemd timer)
Edge TLS certs:    certificados con TTL 1 año, renovación automatizada
SSH host key:      no rotar (rompe known_hosts de operator)
Backup age key:    rotar cada 12 meses, mantener clave anterior 90 días para decrypt de backups antiguos
```

## Healthchecks

### Healthcheck endpoint (`GET /health`)
```json
{
  "status": "ok",
  "services": {
    "discovery": "running",
    "extraction": "running",
    "quality": "running",
    "nlg_last_run": "2026-04-14T00:30:00Z",
    "index": "running",
    "api": "running"
  },
  "vehicles_active": 12453,
  "dealers_indexed": 3821,
  "confidence_p50": 0.72,
  "uptime_seconds": 1234567
}
```

### Systemd watchdog (para servicios críticos)
```ini
# En api.service, quality.service, index.service
WatchdogSec=30s
# El proceso Go debe hacer sd_notify("WATCHDOG=1") cada <30s
# Si falla → systemd reinicia el servicio automáticamente
```

### Checks manuales de rutina (diarios)
```bash
#!/bin/bash
# /usr/local/bin/cardex-daily-check.sh
systemctl is-active --quiet cardex-discovery && echo "discovery: OK" || echo "discovery: FAIL"
systemctl is-active --quiet cardex-extraction && echo "extraction: OK" || echo "extraction: FAIL"
systemctl is-active --quiet cardex-quality && echo "quality: OK" || echo "quality: FAIL"
systemctl is-active --quiet cardex-api && echo "api: OK" || echo "api: FAIL"
sqlite3 /srv/cardex/db/main.db "SELECT COUNT(*) FROM vehicle_record WHERE status='ACTIVE';"
df -h /srv | tail -1
```
