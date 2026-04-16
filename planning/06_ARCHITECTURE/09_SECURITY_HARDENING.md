# 09 — Security Hardening

## Identificador
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Modelo de amenaza

CARDEX es una plataforma B2B con datos públicamente accesibles (vehículos indexados de fuentes públicas). Las amenazas prioritarias son:

1. **Acceso no autorizado al VPS** — SSH brute force, exploit de dependencias
2. **Manipulación del pipeline de calidad** — modificación de código para inyectar técnicas ilegales
3. **Exfiltración del knowledge graph** — API abuse, SQLite file access
4. **Exposición de secrets** — API keys B2B, credenciales de backup
5. **DDoS sobre la API** — agotamiento de recursos del VPS
6. **Dependencia maliciosa en Go modules** — supply chain attack

---

## OS Hardening — Debian 12 CIS Benchmark (subset aplicado)

### Configuración del kernel (sysctl)
```ini
# /etc/sysctl.d/99-cardex-hardening.conf

## Network: prevención de ataques comunes
net.ipv4.tcp_syncookies = 1                    # SYN flood protection
net.ipv4.conf.all.rp_filter = 1                # Reverse path filtering
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0         # No ICMP redirect
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1
net.ipv4.tcp_timestamps = 0                    # Reducir fingerprinting
net.ipv4.conf.all.log_martians = 1             # Log martian packets

## Memory: ASLR + restricciones kernel
kernel.randomize_va_space = 2                  # Full ASLR
kernel.dmesg_restrict = 1                      # Solo root puede leer dmesg
kernel.kptr_restrict = 2                       # Ocultar kernel pointers en /proc
kernel.sysrq = 0                               # Deshabilitar SysRq
kernel.core_dumps_disabled = 1
fs.suid_dumpable = 0

## File descriptors (para SQLite + DuckDB con muchos file handles)
fs.file-max = 200000

## TCP hardening
net.ipv4.tcp_rfc1337 = 1
net.ipv4.tcp_fin_timeout = 15
net.ipv4.tcp_keepalive_time = 300
net.ipv4.tcp_max_syn_backlog = 4096
```

### Módulos del kernel (deshabilitar innecesarios)
```ini
# /etc/modprobe.d/cardex-blacklist.conf
install cramfs /bin/true
install freevxfs /bin/true
install jffs2 /bin/true
install hfs /bin/true
install hfsplus /bin/true
install squashfs /bin/true
install udf /bin/true
install usb-storage /bin/true        # Sin dispositivos USB en VPS
install firewire-core /bin/true
```

---

## Firewall — UFW (Uncomplicated Firewall)

```bash
# Política por defecto
ufw default deny incoming
ufw default allow outgoing    # Crawling requiere outbound libre
ufw default deny forward

# Reglas de entrada
ufw allow 22/tcp    # SSH (considera mover a puerto no estándar, e.g. 2222)
ufw allow 443/tcp   # HTTPS (Caddy, único punto de entrada público)
ufw allow 80/tcp    # HTTP (solo para redirect a HTTPS via Caddy)

# Todos los puertos internos (3001, 3002, 8888, 9090, etc.) NO expuestos
# Solo accesibles via SSH tunnel desde el operator

ufw enable
ufw logging on
```

### Reglas iptables adicionales (protección DDoS básica)
```bash
# Rate limiting de conexiones nuevas por IP (DDoS mitigation)
iptables -A INPUT -p tcp --dport 443 -m conntrack --ctstate NEW -m recent \
    --set --name HTTPS_RATE
iptables -A INPUT -p tcp --dport 443 -m conntrack --ctstate NEW -m recent \
    --update --seconds 60 --hitcount 120 --name HTTPS_RATE -j DROP

# Guardar reglas
iptables-save > /etc/iptables/rules.v4
```

---

## SSH Hardening

```ini
# /etc/ssh/sshd_config.d/99-cardex.conf
Port 22
Protocol 2

# Autenticación
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
AuthorizedKeysFile /home/cardex/.ssh/authorized_keys
ChallengeResponseAuthentication no
UsePAM no

# Algoritmos modernos únicamente
KexAlgorithms curve25519-sha256,curve25519-sha256@libssh.org,diffie-hellman-group16-sha512,diffie-hellman-group18-sha512
HostKeyAlgorithms ssh-ed25519,rsa-sha2-512,rsa-sha2-256
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com
MACs hmac-sha2-256-etm@openssh.com,hmac-sha2-512-etm@openssh.com,umac-128-etm@openssh.com

# Restricciones de sesión
LoginGraceTime 30
MaxAuthTries 3
MaxSessions 5
ClientAliveInterval 300
ClientAliveCountMax 2

# Usuarios permitidos
AllowUsers cardex

# Deshabilitar features innecesarios
X11Forwarding no
PrintLastLog yes
Banner /etc/ssh/cardex-banner.txt
```

```
# /etc/ssh/cardex-banner.txt
CARDEX Platform — Authorized Access Only
All connections are logged and monitored.
Unauthorized access is prohibited.
```

---

## Fail2ban

```ini
# /etc/fail2ban/jail.d/cardex.conf

[DEFAULT]
bantime = 3600      # 1 hora de ban
findtime = 600      # ventana de detección 10 min
maxretry = 5
backend = systemd

[sshd]
enabled = true
port = ssh
maxretry = 3
bantime = 86400     # 24h ban para SSH (más estricto)

[cardex-api]
# Protección contra API abuse (requiere log parsing)
enabled = true
port = 443
filter = cardex-api-ratelimit
logpath = /var/log/caddy/access.log
maxretry = 200      # >200 req en 10 min desde una IP → ban
bantime = 3600
findtime = 600

[caddy-auth]
# Ban IPs con 401/403 repetidos (intentos de acceso no autorizado a /review o /edge)
enabled = true
port = 443
filter = caddy-auth-failures
logpath = /var/log/caddy/access.log
maxretry = 10
bantime = 7200
```

```ini
# /etc/fail2ban/filter.d/cardex-api-ratelimit.conf
[Definition]
failregex = ^.*"remote_ip":"<HOST>".*"status":429.*$
ignoreregex =
```

---

## Automatic Security Updates

```ini
# /etc/apt/apt.conf.d/50unattended-upgrades
Unattended-Upgrade::Allowed-Origins {
    "Debian:bookworm";
    "Debian:bookworm-security";
};

Unattended-Upgrade::Package-Blacklist {
    # No actualizar automáticamente Go runtime ni Docker (coordinación manual)
};

Unattended-Upgrade::AutoFixInterruptedDpkg "true";
Unattended-Upgrade::MinimalSteps "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";  # fuera de ventana NLG
Unattended-Upgrade::SyslogEnable "true";
Unattended-Upgrade::SyslogFacility "daemon";
```

---

## TLS Configuration (Caddy)

Caddy gestiona TLS automáticamente con Let's Encrypt (ACME). La configuración fuerza Mozilla "Modern" compatibility profile:

```
TLS versions: TLS 1.3 exclusivamente
Cipher suites (TLS 1.3): TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256
HSTS: max-age=31536000; includeSubDomains; preload
OCSP Stapling: automático (Caddy)
Certificate Transparency: automático (Let's Encrypt)
```

### mTLS para Edge Client (E11)
```
CA privada: generada en el VPS con openssl (self-signed CA)
Certificados cliente: emitidos por operator para cada dealer E11
Validez: 1 año con renovación automatizada via edge client
Revocación: CRL file servida por Caddy en /edge-crl.pem
```

---

## Systemd User Services (Least Privilege)

```bash
# Usuario de sistema para todos los servicios CARDEX
useradd --system --no-create-home --shell /usr/sbin/nologin cardex
# UID/GID asignado por sistema (~999)

# Permisos de directorios (principio de least privilege)
chown -R root:cardex /srv/cardex
chmod 750 /srv/cardex

chown root:cardex /srv/cardex/db
chmod 770 /srv/cardex/db         # read+write solo para grupo cardex

chown root:cardex /srv/cardex/models
chmod 750 /srv/cardex/models     # read-only para cardex

# Binarios: root-owned, executable por cardex
chown root:root /usr/local/bin/cardex-*
chmod 755 /usr/local/bin/cardex-*
```

### Sandboxing systemd (aplicado a todos los servicios)
```ini
# Directivas de seguridad systemd aplicadas a todos los .service
NoNewPrivileges=yes           # No puede adquirir más privilegios
PrivateTmp=yes                # /tmp privado y aislado
ProtectSystem=strict          # / y /usr read-only
ProtectHome=yes               # /home, /root, /run/user inaccesibles
PrivateDevices=yes            # Sin acceso a /dev/* excepto null/random/urandom
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX  # Solo IPv4, IPv6, Unix sockets
RestrictNamespaces=yes        # Sin creación de namespaces
LockPersonality=yes           # Sin cambio de personalidad del proceso
MemoryDenyWriteExecute=yes    # Sin páginas ejecutables write+exec (protege contra shellcode)
RestrictSUIDSGID=yes          # Sin binarios SUID/SGID desde el proceso
SystemCallFilter=@system-service  # Solo syscalls necesarios para servicios típicos
```

---

## AppArmor

```apparmor
# /etc/apparmor.d/usr.local.bin.cardex-api
#include <tunables/global>

/usr/local/bin/cardex-api flags=(complain) {
    #include <abstractions/base>
    #include <abstractions/nameservice>

    # Acceso permitido
    /srv/cardex/db/discovery.db r,
    /srv/cardex/olap/ r,
    /srv/cardex/olap/** r,
    /srv/cardex/www/ r,
    /srv/cardex/www/** r,
    /run/cardex-api/ rw,
    /run/cardex-api/** rw,
    /run/credentials/cardex-api/** r,

    # Network (API server)
    network inet stream,
    network inet6 stream,
    network unix stream,

    # Denegado explícitamente
    deny /srv/cardex/models/** rw,    # API no necesita acceder a modelos ML
    deny /etc/ssh/** rw,
    deny /root/** rw,

    # Capabilities
    capability net_bind_service,
}
```

---

## Auditd (Log de auditoría)

```bash
# /etc/audit/rules.d/cardex.rules

# Monitorizar cambios en binarios CARDEX
-w /usr/local/bin/cardex-discovery -p wa -k cardex_binary_change
-w /usr/local/bin/cardex-extraction -p wa -k cardex_binary_change
-w /usr/local/bin/cardex-quality -p wa -k cardex_binary_change
-w /usr/local/bin/cardex-api -p wa -k cardex_binary_change

# Monitorizar cambios en configuración de secrets
-w /etc/cardex/credentials/ -p wa -k cardex_secret_change

# Monitorizar accesos a la base de datos desde fuera del proceso esperado
-a always,exit -F arch=b64 -S open,openat -F path=/srv/cardex/db/discovery.db \
    -F uid!=999 -k unauthorized_db_access

# Monitorizar cambios en SSH config
-w /etc/ssh/sshd_config -p wa -k ssh_config_change

# Monitorizar escalada de privilegios
-a always,exit -F arch=b64 -S setuid -F a0=0 -k privilege_escalation
-a always,exit -F arch=b64 -S setgid -F a0=0 -k privilege_escalation

# Monitorizar crontabs
-w /etc/cron.d/ -p wa -k cron_change
-w /var/spool/cron/ -p wa -k cron_change
```

---

## Go Dependency Security

### go.sum verification
```bash
# Verificación de integridad de módulos en cada build
GONOSUMCHECK="" GOFLAGS="-mod=verify" go build ./...
```

### Dependency audit en CI (Forgejo pipeline step)
```bash
# Usando govulncheck (Google vulnerability database)
govulncheck ./...

# Verificar que no hay módulos reemplazados (replace directives sospechosas)
grep -r "^replace" go.mod && echo "WARNING: replace directives found" || echo "OK"

# Dependency blacklist check
BLACKLISTED_PKGS=(
    "github.com/refraction-networking/utls"     # TLS fingerprint evasion
    "github.com/Danny-Dasilva/CycleTLS"         # TLS fingerprint evasion
    "github.com/bogdanfinn/tls-client"           # TLS fingerprint evasion
)
for pkg in "${BLACKLISTED_PKGS[@]}"; do
    if grep -r "$pkg" go.mod go.sum 2>/dev/null; then
        echo "ILLEGAL DEPENDENCY: $pkg"
        exit 1
    fi
done
```

---

## Gestión de Secrets — Rotación

| Secret | Tipo | Rotación | Proceso |
|---|---|---|---|
| SSH authorized key | Ed25519 public key | Anual o si se sospecha compromiso | Nuevo par, actualizar authorized_keys, revocar anterior |
| API key salt | HMAC secret 256-bit | 90 días | Generar nuevo salt, revocar keys antiguas, notificar a buyers B2B con 7 días de aviso |
| Edge client TLS cert | X.509 client cert | Anual | CA firma nuevo cert, edge client lo descarga en siguiente sync |
| Backup age key | X25519 keypair | Anual | Mantener clave anterior 90 días para decrypt de backups, luego purgar |
| Grafana admin password | bcrypt hash | 180 días | Actualizar via API Grafana, invalidar sesiones activas |

---

## Checklist de Security Review (mensual)

```
□ Revisar fail2ban bans: tendencias inesperadas de IPs baneadas
□ Revisar auditd logs: accesos anómalos a db/credentials
□ Revisar unattended-upgrades: updates aplicados correctamente
□ Verificar TLS cert expiration: >30 días de vigencia
□ Revisar logs de Forgejo: commits desde IPs/usuarios inesperados
□ Ejecutar govulncheck: 0 vulnerabilidades known en dependencias Go
□ Revisar ufw deny logs: patrones de scanning
□ Verificar backups: decrypt y restauración de un backup reciente
□ Revisar AppArmor complain log: accesos no autorizados emergentes
```
