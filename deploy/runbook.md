# CARDEX — VPS Provisioning Runbook

**Operator:** Salman  
**VPS:** Hetzner CX42 (4 vCPU AMD EPYC, 16 GB RAM, 240 GB NVMe)  
**OS:** Debian 12 (Bookworm) minimal  
**Domain:** cardex.io  
**Est. OPEX:** ~€22/month (VPS ~€18 + Storage Box ~€3 + domain ~€1.25)  

---

## Prerequisites

Before starting, have ready:
- [ ] KeePassXC with `cardex-secrets.kdbx`
- [ ] SSH public key (from `deploy/secrets/id_ed25519.pub` or KeePassXC)
- [ ] age backup public key (from `deploy/secrets/backup-pubkey.txt`)
- [ ] Hetzner Cloud account

---

## Step 1: Provision Hetzner CX42

1. Log in to [Hetzner Cloud Console](https://console.hetzner.cloud/)
2. Create new server:
   - **Type:** CX42 (AMD)
   - **Location:** Nürnberg (NBG1) for DE/AT/CH low latency
   - **Image:** Debian 12
   - **SSH Key:** paste content of `deploy/secrets/id_ed25519.pub`
   - **Name:** `cardex-prod`
3. Note the assigned IP address.
4. Update DNS: `A cardex.io → <VPS IP>`, `CNAME www → cardex.io`
5. Wait for DNS propagation (5–60 min).

---

## Step 2: Initial SSH + system hardening

```bash
# Connect as root (first time only)
ssh -i deploy/secrets/id_ed25519 root@<VPS-IP>

# Update system
apt update && apt upgrade -y

# Install essentials
apt install -y \
    git curl wget rsync sqlite3 age \
    ufw fail2ban unattended-upgrades \
    ca-certificates gnupg lsb-release

# Create non-root operator user
useradd -m -s /bin/bash -G sudo cardex
mkdir -p /home/cardex/.ssh
cp /root/.ssh/authorized_keys /home/cardex/.ssh/
chown -R cardex:cardex /home/cardex/.ssh
chmod 700 /home/cardex/.ssh
chmod 600 /home/cardex/.ssh/authorized_keys

# Create service directories
mkdir -p /srv/cardex/{db,backups,prometheus,grafana,alertmanager,caddy/{data,config}}
mkdir -p /opt/cardex
mkdir -p /etc/cardex/credentials
chown -R cardex:cardex /srv/cardex /opt/cardex /etc/cardex
```

---

## Step 3: SSH hardening

```bash
# /etc/ssh/sshd_config (edit as root)
cat >> /etc/ssh/sshd_config <<'EOF'
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
Protocol 2
LoginGraceTime 30
MaxAuthTries 3
AllowUsers cardex
EOF

systemctl restart ssh

# Test new config BEFORE closing current session:
ssh -i deploy/secrets/id_ed25519 cardex@<VPS-IP> echo "SSH as cardex: OK"
```

---

## Step 4: Firewall (ufw)

```bash
# As root:
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp      # SSH
ufw allow 80/tcp      # Caddy ACME HTTP-01 challenge
ufw allow 443/tcp     # HTTPS
ufw enable
ufw status verbose
```

---

## Step 5: Docker installation (for observability stack)

```bash
# Official Docker install (as root):
curl -fsSL https://get.docker.com | sh
usermod -aG docker cardex

# Verify
docker --version
docker compose version
```

---

## Step 6: Clone repo + build services

```bash
# As user cardex:
su - cardex

git clone https://github.com/cardex/cardex.git /opt/cardex
# (or Forgejo URL when self-hosted Forgejo is running)

cd /opt/cardex

# Install Go 1.25
export GOVERSION=1.25.0
curl -OL "https://go.dev/dl/go${GOVERSION}.linux-amd64.tar.gz"
sudo tar -C /usr/local -xzf "go${GOVERSION}.linux-amd64.tar.gz"
export PATH=$PATH:/usr/local/go/bin
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc

# Build all services
cd /opt/cardex/discovery  && GOWORK=off go build -o /usr/local/bin/cardex-discovery ./cmd/discovery-service/
cd /opt/cardex/extraction && GOWORK=off go build -o /usr/local/bin/cardex-extraction ./cmd/extraction-service/
cd /opt/cardex/quality    && GOWORK=off go build -o /usr/local/bin/cardex-quality ./cmd/quality-service/
sudo chmod +x /usr/local/bin/cardex-{discovery,extraction,quality}
```

---

## Step 7: Configure secrets

```bash
# On your local machine — generate secrets:
./deploy/scripts/secrets-generate.sh

# Copy public key to VPS (private key stays local + KeePassXC):
scp -i deploy/secrets/id_ed25519 \
    deploy/secrets/backup-pubkey.txt \
    cardex@<VPS-IP>:/etc/cardex/backup-pubkey.txt

# On VPS — store credentials via systemd-creds:
# (replace values with actual credentials from KeePassXC)
sudo bash -c "echo 'u123456.your-storagebox.de' | \
    systemd-creds encrypt --name=storage-box-host -p - \
    /etc/cardex/credentials/storage-box-host"

sudo bash -c "echo 'u123456' | \
    systemd-creds encrypt --name=storage-box-user -p - \
    /etc/cardex/credentials/storage-box-user"

# Add Hetzner Storage Box SSH key to cardex user:
ssh-keygen -t ed25519 -f /home/cardex/.ssh/storage-box -N ""
# Add content of storage-box.pub to Hetzner Storage Box via the panel
```

---

## Step 8: Install systemd units

```bash
# Copy unit files:
sudo cp /opt/cardex/deploy/systemd/cardex-discovery.service  /etc/systemd/system/
sudo cp /opt/cardex/deploy/systemd/cardex-extraction.service /etc/systemd/system/
sudo cp /opt/cardex/deploy/systemd/cardex-quality.service    /etc/systemd/system/
sudo cp /opt/cardex/deploy/systemd/cardex-backup.service     /etc/systemd/system/
sudo cp /opt/cardex/deploy/systemd/cardex-backup.timer       /etc/systemd/system/

# Copy backup script:
sudo cp /opt/cardex/deploy/scripts/backup.sh /opt/cardex/scripts/backup.sh
sudo chmod +x /opt/cardex/scripts/backup.sh

# Enable and start:
sudo systemctl daemon-reload
sudo systemctl enable --now cardex-discovery
sudo systemctl enable --now cardex-extraction
sudo systemctl enable --now cardex-quality
sudo systemctl enable --now cardex-backup.timer

# Verify:
sudo systemctl status cardex-discovery cardex-extraction cardex-quality
sudo journalctl -u cardex-discovery -n 30
```

---

## Step 9: Start observability stack (Docker Compose)

```bash
cd /opt/cardex

# Start Prometheus + Grafana + Alertmanager:
docker compose \
    -f deploy/docker/docker-compose.yml \
    -f deploy/docker/docker-compose.prod.yml \
    up -d prometheus grafana alertmanager

# Verify Prometheus is scraping:
sleep 30
curl http://localhost:9090/api/v1/targets | python3 -m json.tool | grep '"health"'
```

---

## Step 10: Install + start Caddy

```bash
# Install Caddy (Debian):
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy

# Copy Caddyfile:
sudo cp /opt/cardex/deploy/caddy/Caddyfile /etc/caddy/Caddyfile
sudo sed -i "s/{\\$CARDEX_DOMAIN:localhost}/cardex.io/g" /etc/caddy/Caddyfile

sudo systemctl enable --now caddy
sudo systemctl status caddy
```

---

## Step 11: Verify end-to-end

```bash
# All services running:
sudo systemctl is-active cardex-discovery cardex-extraction cardex-quality caddy

# Health endpoint (from external machine):
curl https://cardex.io/health
# Expected: "OK"

# Metrics:
curl http://localhost:9101/metrics | head -20
curl http://localhost:9102/metrics | head -20
curl http://localhost:9103/metrics | head -20

# Access Grafana via SSH tunnel:
# (from local machine)
ssh -L 3001:localhost:3001 cardex@cardex.io
# Open http://localhost:3001 — login: admin / <GRAFANA_ADMIN_PASSWORD>
```

---

## Step 12: External monitor

Set up health check on a separate machine (Oracle Cloud Free Tier):

```bash
# On monitor machine:
git clone https://github.com/cardex/cardex.git /opt/cardex-monitor
cp /opt/cardex-monitor/deploy/scripts/health-check.sh /opt/cardex-monitor/

# Configure:
export CARDEX_URL=https://cardex.io
export ALERT_EMAIL=operator@example.com

# Add to crontab:
crontab -e
# Add: */5 * * * * CARDEX_URL=https://cardex.io ALERT_EMAIL=you@example.com \
#        /opt/cardex-monitor/health-check.sh >> /var/log/cardex-health.log 2>&1
```

---

## Maintenance

### Deploy update
```bash
./deploy/scripts/deploy.sh cardex@cardex.io production
```

### Manual backup
```bash
sudo systemctl start cardex-backup
sudo journalctl -u cardex-backup -f
```

### Check backup freshness
```bash
ls -lh /srv/cardex/backups/
```

### Rollback
```bash
ssh cardex@cardex.io "
    cd /opt/cardex
    git log --oneline -5   # find previous commit hash
    git checkout <hash>
    # rebuild:
    cd discovery && GOWORK=off go build -o /usr/local/bin/cardex-discovery ./cmd/discovery-service/
    sudo systemctl restart cardex-discovery
"
```

### Incident response
See `planning/06_ARCHITECTURE/13_RUNBOOK.md` for full P0/P1/P2 incident decision trees.

---

## Sysctl hardening (apply once)

```bash
cat > /etc/sysctl.d/99-cardex.conf <<'EOF'
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.tcp_timestamps = 0
kernel.randomize_va_space = 2
kernel.dmesg_restrict = 1
kernel.kptr_restrict = 2
fs.file-max = 200000
EOF
sysctl -p /etc/sysctl.d/99-cardex.conf
```
