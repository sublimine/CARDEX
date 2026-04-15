# CARDEX — ESPECIFICACIÓN CANÓNICA DE IMPLEMENTACIÓN

**Versión:** 1.0.0-SEALED  
**Fecha de sellado:** 2026-02-27  
**Fuentes consolidadas:** V1 (386pp), V2 (292pp), V3 (74pp), V4 (32pp), V5 (91pp), V6 (49pp) — 924 páginas totales  
**Destinatario:** Ingeniero senior con acceso exclusivo a este documento y un IDE (Cursor/Aider)  
**Régimen de verdad:** Cuando V6 contradice versiones anteriores, V6 prevalece. V2 prevalece en lógica de negocio. V5 prevalece en runbooks cuando V6 no los redefine. V4 queda purgado de elementos ilegales; solo se conservan sus contribuciones técnicas legítimas.

> **NOTA DE IMPLEMENTACIÓN (2026-04-15):** Este documento describe la visión completa y ambiciosa de CARDEX (3× Hetzner AX102, PostgreSQL 16, ClickHouse, stack completo de microservicios). Las Fases 2–5 implementadas en `claude/objective-wilbur` son un **MVP deliberadamente más simple**: un único servidor CX42 (~€22/mes), SQLite, tres servicios Go (discovery/extraction/quality), sin PostgreSQL ni ClickHouse. El MVP es el punto de partida hacia la visión completa descrita aquí. Para el estado actual de implementación, ver `CONTEXT_FOR_AI.md`.

---

## CONTRADICCIONES RESUELTAS ENTRE VERSIONES (REGISTRO INMUTABLE)

| # | Tema | V anterior | V6 (Prevalece) | Justificación |
|---|------|------------|-----------------|---------------|
| C-01 | Thermal Management | V4/V5: PBO desbloqueado a 95°C sin límite | V6: Eco-Mode 105W PPT estricto (RyzenAdj) | 95°C sostenido genera Clock Jitter que destruye el determinismo HFT. 105W garantiza frecuencias planas 24/7 |
| C-02 | Sandboxing de Ingesta | V4/V5: Firecracker MicroVMs (KVM) | V6: Bubblewrap + Seccomp (Kernel Namespaces) | Firecracker añade ~300µs de overhead I/O por boot. Bubblewrap opera a 0µs mediante aislamiento nativo del kernel |
| C-03 | Compilación AVX-512 | V4/V5: `-march=znver4` con AVX-512 habilitado | V6: `-mno-avx512f` para purgar AVX-512 | AVX-512 provoca throttling térmico en Zen 4 al activar unidades de 512 bits. La ganancia de throughput no compensa la pérdida de frecuencia y el jitter resultante bajo PPT=105W |
| C-04 | Scraping / Extracción | V4: SSL Unpinning (Frida), API Ghosting, Dark Web | V6: B2B Webhooks licenciados (Arval, BCA, LeasePlan) | V4 constituye infracción penal (Art. 197 CP, CFAA). V6 opera exclusivamente con feeds licenciados y APIs B2B oficiales |
| C-05 | Telecom | V4: DID Spoofing ilegal, SS7 HLR sin autorización | V6: Twilio SIP con DIDs legales y STIR/SHAKEN compliance | Caller ID Spoofing viola la Communications Act. V6 alquila DIDs verificados bajo KYC corporativo |
| C-06 | Infraestructura Cloud | V1: AWS Serverless, LangGraph multi-LLM | V3/V6: Hetzner AX102 bare-metal, 3-node cluster | Bare-metal reduce OPEX de ~2.800€/mes (AWS) a ~327€/mes. LangGraph se sustituye por orquestación determinista en Go/Rust |
| C-07 | Modelo de IA | V1: GPT-3.5/GPT-4 cloud routing | V5/V6: Qwen2.5-7B + Phi-3.5 + Nomic local (GGUF) | Soberanía de datos total (Zero-Cloud). Coste de inferencia: 0€/token. Latencia: <50ms local vs ~300ms API |
| C-08 | Pricing / Créditos | V1: SaaS puro (Básico/Completo/Premium) | V6: Créditos de Computación con caducidad 90d (Anti-MiCA) | SaaS puro no elude la clasificación EMI/PSD2. Créditos con TTL y no-refund evitan regulación bancaria |
| C-09 | Replicación DB | V5: MaterializedPostgreSQL experimental | V6: Idéntico pero con Schema Watchdog obligatorio | El motor experimental colapsa ante DDL changes. El Watchdog pausa/recrea la suscripción atómicamente |
| C-10 | Dark Pool Penalización | V4: Slashing financiero (deducción de saldo) | V6: Karma Slashing (reputación) + Shadow Ban latencia | Slashing financiero genera Chargebacks y litigios. Karma + latencia artificial castiga sin consecuencias legales |

---

## FASE 0: FUNDACIÓN BARE-METAL, AISLAMIENTO NATIVO Y DETERMINISMO TÉRMICO

### 0.0. QUÉ HACE

Despliega la capa de silicio sobre la que opera todo el sistema. Tres nodos Hetzner AX102 (AMD Ryzen 9 7950X3D, 16C/32T, 128GB DDR5 ECC, 2× NVMe Gen4 datacenter-grade) configurados como clúster bare-metal con aislamiento NUMA estricto, determinismo térmico perpetuo y red interna sin fragmentación. El resultado es una plataforma de cómputo con latencia de I/O submilisegundo, inmune a jitter térmico, capaz de sostener ingesta continental (12M activos/hora) y procesamiento HFT simultáneo.

### 0.1. POR QUÉ ASÍ Y NO DE OTRA FORMA

**Bare-metal vs. Cloud (AWS/GCP):** El coste operativo mensual de un clúster equivalente en AWS (3× m5.8xlarge + EBS io2 + NAT Gateway + transfer) se estima en ~2.800€/mes. Tres AX102 de Hetzner cuestan 327€/mes combinados (109€/nodo). A 36 meses, la diferencia acumulada supera los 89.000€. Además, el bare-metal elimina la "impuesto de latencia" del hipervisor compartido (~15-30µs por syscall virtualizada) y garantiza acceso exclusivo al bus PCIe y a los controladores NVMe — crítico para operaciones io_uring de zero-copy.

**105W PPT vs. PBO desbloqueado:** El Ryzen 9 7950X3D con PBO activo escala hasta 162W y 95°C. A esa temperatura sostenida, el System Management Controller (SMC) ejecuta Clock Stretching: inserta ciclos de reloj nulos para enfriar el silicio. Esto genera variaciones de latencia de ±15% entre ejecuciones consecutivas de la misma operación — letal para un sistema que cotiza precios en tiempo real y ejecuta Mutex atómicos con ventanas de nanosegundos. Sellar el PPT a 105W mediante RyzenAdj (stapm-limit=105000, fast-limit=105000, slow-limit=105000, tctl-temp=80) garantiza frecuencias planas (all-core ~4.2GHz sostenidos) con varianza <0.5%. El tradeoff es ~18% menos throughput pico en ráfagas cortas, pero el sistema opera 24/7 — no necesita picos, necesita predictibilidad.

**Bubblewrap vs. Firecracker:** Firecracker (KVM minimalista) arranca en ~125ms y consume ~300µs de overhead I/O por operación debido a la capa de virtualización del disco virtio. Cuando el pipeline procesa 50.000 JSONs/segundo procedentes del enjambre, ese overhead acumula 15 segundos de CPU desperdiciada por minuto. Bubblewrap opera directamente sobre Linux Namespaces y Seccomp-BPF: crea un sandbox efímero en 0µs de overhead (no hay booteo, no hay kernel guest, no hay virtio). El perfil Seccomp restringe las syscalls a {read, write, close, exit_group, brk, mmap, munmap, mprotect} — si un JSON hostil intenta abrir un socket o ejecutar un fork(), el kernel mata el proceso instantáneamente.

### 0.2. IMPLEMENTACIÓN EXACTA

#### 0.2.1. Topología NUMA y Secuestro del Planificador

El AMD Ryzen 9 7950X3D contiene dos Core Complex Dies (CCD) conectados por el bus Infinity Fabric. CCD0 integra 128MB de 3D V-Cache apilada sobre los 8 cores físicos (16 lógicos con SMT). CCD1 carece de V-Cache pero opera a frecuencias ligeramente superiores en cargas monohilo. La latencia de acceso cross-CCD (core de CCD0 accediendo a RAM del controlador de CCD1) penaliza ~40ns respecto al acceso local.

El planificador del kernel Linux se interviene a nivel de bootloader GRUB para impedir que el SO migre procesos entre CCDs:

```bash
# /etc/default/grub — Inyección de parámetros de kernel
GRUB_CMDLINE_LINUX_DEFAULT="quiet isolcpus=0-15 nohz_full=0-15 rcu_nocbs=0-15 mitigations=off pcie_aspm=off ipv6.disable=1 tsc=reliable"
```

Desglose de cada parámetro:

- `isolcpus=0-15`: Retira los cores lógicos 0-15 (CCD0) del planificador general. Solo los procesos explícitamente asignados via `taskset` o `numactl` pueden ejecutarse en ellos. Esto reserva CCD0 exclusivamente para las bases de datos (PostgreSQL, ClickHouse).
- `nohz_full=0-15`: Desactiva las interrupciones de reloj (timer ticks) en CCD0. Un tick genera un context switch de ~1µs cada 4ms (CONFIG_HZ=250). En 16 cores, eso son 4.000 interrupciones/segundo eliminadas.
- `rcu_nocbs=0-15`: Desplaza los callbacks de Read-Copy-Update (mecanismo de sincronización del kernel) fuera de CCD0 hacia CCD1. Elimina las ráfagas de latencia impredecible causadas por el recolector de garbage del kernel.
- `mitigations=off`: Desactiva las mitigaciones de Spectre/Meltdown. En bare-metal single-tenant sin VMs compartidas, estas mitigaciones consumen ~5-8% de rendimiento sin beneficio de seguridad.
- `pcie_aspm=off`: Desactiva el Power Management del bus PCIe. Evita que los controladores NVMe entren en estados de bajo consumo que añaden ~100µs de wake-up latency.
- `ipv6.disable=1`: Elimina el stack IPv6 completo. Reduce la superficie de ataque y el procesamiento de paquetes no utilizados.
- `tsc=reliable`: Declara el Time Stamp Counter como fuente de tiempo fiable. Permite que `clock_gettime()` se resuelva en userspace (vDSO) sin syscall, reduciendo la latencia de timestamping a <15ns.

Asignación de dominios:

| Dominio | Cores Lógicos | CCD | Función | Características |
|---------|---------------|-----|---------|-----------------|
| Transaccional (BBDD) | 0-15 | CCD0 | PostgreSQL, ClickHouse, Redis, PgBouncer | 128MB 3D V-Cache. Timer ticks desactivados. Acceso exclusivo a NVMe primario via io_uring |
| Red + IA | 16-31 | CCD1 | Gateway QUIC, llama-server, Workers Go/Python | Sin V-Cache. Frecuencia pico superior. Absorbe interrupciones de red y syscalls del sistema |

#### 0.2.2. Determinismo Térmico (RyzenAdj 105W Lock)

```bash
# Instalación y compilación de RyzenAdj
apt-get update && apt-get install -y linux-cpupower msr-tools build-essential cmake git
git clone https://github.com/FlyGoat/RyzenAdj.git /opt/RyzenAdj
cd /opt/RyzenAdj && mkdir build && cd build && cmake -DCMAKE_BUILD_TYPE=Release .. && make
cp ryzenadj /usr/local/bin/

# Forzar governor 'performance' (frecuencia máxima constante dentro del PPT)
cpupower frequency-set -g performance
```

Servicio systemd que aplica el sello térmico en cada arranque:

```bash
cat << 'EOF' > /etc/systemd/system/cardex-thermal-lock.service
[Unit]
Description=Cardex Hardware Thermal Determinism (105W Strict PPT)
After=multi-user.target

[Service]
Type=oneshot
# PPT = Package Power Tracking: Límite absoluto de potencia del paquete
# STAPM = Skin Temperature Aware Power Management: Media móvil a largo plazo
# TDC = Thermal Design Current: Límite de corriente sostenida
# EDC = Electrical Design Current: Límite de corriente pico
# tctl-temp = 80°C: Temperatura objetivo del die (20°C por debajo del límite crítico de 100°C)
ExecStart=/usr/local/bin/ryzenadj --stapm-limit=105000 --fast-limit=105000 --slow-limit=105000 --tctl-temp=80
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now cardex-thermal-lock
```

Verificación del sello:

```bash
# Debe reportar PPT STAPM = 105W, PPT Fast = 105W, PPT Slow = 105W
ryzenadj -i | grep -E "PPT|STAPM|TDC|EDC"
# Bajo carga sostenida (stress-ng -c 32 -t 60), la temperatura no debe superar 80°C
# y la frecuencia all-core debe permanecer estable en ±50MHz
```

#### 0.2.3. Particionado Físico Asimétrico (ZFS / XFS / RAW)

El sistema opera con dos discos NVMe Gen4 datacenter-grade. El particionado elimina la colisión entre el ARC cache de ZFS y el PageCache de Linux, que en configuración estándar compiten por la misma RAM y generan double-caching destructivo.

```bash
apt-get install -y zfsutils-linux xfsprogs gdisk

# === DISCO 1 (/dev/nvme0n1): Transaccional + Buffer de Ingesta ===

sgdisk -Z /dev/nvme0n1  # Destruir tabla de particiones previa

# Partición 1: RAW (10GB) — Redis AOF (Append-Only File)
# Sin filesystem. Redis escribe directamente al dispositivo de bloques.
# Latencia de escritura: <20µs. RPO=0 (Recovery Point Objective: cero pérdida de datos).
sgdisk -n 1:0:+10G -t 1:8300 -c 1:"REDIS_ZIL_RAW" /dev/nvme0n1

# Partición 2: ZFS Pool — PostgreSQL + Vault + SO
sgdisk -n 2:0:0 -t 2:8300 -c 2:"ZFS_ROOT_PG" /dev/nvme0n1

# Estrangulamiento del ARC de ZFS a 16GB máximos
# Sin este límite, ZFS consumiría hasta 90% de la RAM disponible,
# dejando sin memoria a ClickHouse y a los modelos de IA.
echo "options zfs zfs_arc_max=17179869184" > /etc/modprobe.d/zfs.conf
update-initramfs -u

# Creación del pool ZFS con compresión LZ4 y alineación a 4K
zpool create -f -o ashift=12 \
  -O compression=lz4 \
  -O atime=off \
  -O recordsize=16k \
  pgpool /dev/nvme0n1p2

# === DISCO 2 (/dev/nvme1n1): Analítico (ClickHouse exclusivo) ===

sgdisk -Z /dev/nvme1n1

# Partición única: XFS para ClickHouse con Direct I/O
# XFS repudia CoW (a diferencia de ZFS), eliminando la amplificación de escritura
# en workloads append-only columnar.
sgdisk -n 1:0:0 -t 1:8300 -c 1:"XFS_CLICKHOUSE" /dev/nvme1n1

mkfs.xfs -f -K -b size=4096 -m crc=1 /dev/nvme1n1p1

mkdir -p /var/lib/clickhouse
echo "/dev/nvme1n1p1 /var/lib/clickhouse xfs noatime,nodiratime,nobarrier,logbufs=8,allocsize=2M 0 0" >> /etc/fstab
mount -a
```

Mapa de almacenamiento resultante:

| Partición | Filesystem | Tamaño | Función | Propietario |
|-----------|-----------|--------|---------|-------------|
| nvme0n1p1 | RAW | 10GB | Redis AOF buffer de ingesta. RPO=0 | Redis (CCD0) |
| nvme0n1p2 | ZFS (LZ4, recordsize=16k, ARC≤16GB) | ~1.9TB | PostgreSQL OLTP, Vault KMS, SO Proxmox | PostgreSQL, Vault (CCD0) |
| nvme1n1p1 | XFS (noatime, Direct I/O) | ~2TB | ClickHouse OLAP columnar | ClickHouse (CCD0) |

#### 0.2.4. Asepsia de Ingesta: Bubblewrap + Seccomp (Zero-Firecracker)

```bash
apt-get install -y bubblewrap libseccomp-dev gcc jq
mkdir -p /opt/cardex-sandbox

# Generador del filtro BPF estricto
cat << 'EOF' > /opt/cardex-sandbox/seccomp_profile.c
#include <seccomp.h>
#include <unistd.h>
#include <fcntl.h>

int main() {
    // SCMP_ACT_KILL: Cualquier syscall no listada mata el proceso
    scmp_filter_ctx ctx = seccomp_init(SCMP_ACT_KILL);

    // Whitelist mínima: solo memoria y I/O de stdio
    seccomp_rule_add(ctx, SCMP_ACT_ALLOW, SCMP_SYS(read), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ALLOW, SCMP_SYS(write), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ALLOW, SCMP_SYS(close), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ALLOW, SCMP_SYS(exit_group), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ALLOW, SCMP_SYS(brk), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ALLOW, SCMP_SYS(mmap), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ALLOW, SCMP_SYS(munmap), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ALLOW, SCMP_SYS(mprotect), 0);

    int fd = open("/opt/cardex-sandbox/strict.bpf", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    seccomp_export_bpf(ctx, fd);
    seccomp_release(ctx);
    close(fd);
    return 0;
}
EOF

gcc /opt/cardex-sandbox/seccomp_profile.c -lseccomp -o /opt/cardex-sandbox/gen_bpf
/opt/cardex-sandbox/gen_bpf

# Wrapper de parseo seguro: todo JSON hostil pasa por este filtro
cat << 'EOF' > /usr/local/bin/safe_json_parse.sh
#!/bin/bash
# bwrap crea un namespace aislado:
# --ro-bind: filesystem read-only (no puede escribir nada)
# --unshare-all: separa PID, net, mount, user namespaces
# --new-session: previene señales desde el host
# --die-with-parent: si el padre muere, el sandbox muere
# --seccomp: inyecta el filtro BPF compilado
bwrap \
  --ro-bind /usr /usr \
  --ro-bind /bin /bin \
  --ro-bind /lib /lib \
  --ro-bind /lib64 /lib64 \
  --symlink usr/lib /lib \
  --symlink usr/lib64 /lib64 \
  --symlink usr/bin /bin \
  --unshare-all \
  --new-session \
  --die-with-parent \
  --seccomp 11 \
  11< /opt/cardex-sandbox/strict.bpf \
  /bin/jq -c '.'
EOF
chmod +x /usr/local/bin/safe_json_parse.sh
```

#### 0.2.5. Red: Jumbo Frames MTU 9000 y eBPF/XDP

```bash
# Detección dinámica de la interfaz interna (VLAN Hetzner vSwitch)
IFACE_INT=$(ip -o -4 route show | grep -E '^10\.' | awk '{print $3}' | head -n 1)
if [ -n "$IFACE_INT" ]; then
  ip link set dev "$IFACE_INT" mtu 9000
  mkdir -p /etc/network/interfaces.d
  echo "post-up ip link set dev $IFACE_INT mtu 9000" > /etc/network/interfaces.d/internal_mtu
fi

# Buffers UDP para ingesta QUIC transcontinental
cat << 'EOF' > /etc/sysctl.d/99-radar-network.conf
net.core.rmem_max = 268435456
net.core.wmem_max = 268435456
net.core.rmem_default = 67108864
net.core.wmem_default = 67108864
net.ipv4.tcp_tw_reuse = 1
net.ipv4.ip_local_port_range = 10000 65535
net.core.netdev_max_backlog = 100000
fs.file-max = 5000000
net.core.busy_read = 50
net.core.busy_poll = 50
EOF
sysctl --system
```

El filtro eBPF/XDP se inyecta en la NIC externa para descartar tráfico no autorizado antes de que el kernel asigne memoria:

```c
// /opt/xdp_quic_filter.c
#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/udp.h>
#include <bpf/bpf_helpers.h>

SEC("xdp")
int xdp_filter_quic(struct xdp_md *ctx) {
    void *data_end = (void *)(long)ctx->data_end;
    void *data     = (void *)(long)ctx->data;

    struct ethhdr *eth = data;
    if ((void *)(eth + 1) > data_end) return XDP_PASS;
    if (eth->h_proto != __constant_htons(ETH_P_IP)) return XDP_PASS;

    struct iphdr *ip = (struct iphdr *)(eth + 1);
    if ((void *)(ip + 1) > data_end) return XDP_PASS;
    if (ip->protocol != IPPROTO_UDP) return XDP_PASS;

    struct udphdr *udp = (void *)ip + (ip->ihl * 4);
    if ((void *)(udp + 1) > data_end) return XDP_PASS;

    // Solo aceptar UDP al puerto QUIC de ingesta (4433)
    // Todo lo demás se descarta a nivel de NIC (cero CPU)
    if (udp->dest != __constant_htons(4433)) {
        return XDP_DROP;
    }
    return XDP_PASS;
}
char _license[] SEC("license") = "GPL";
```

```bash
apt-get install -y clang llvm libbpf-dev linux-headers-$(uname -r)
IFACE_EXT=$(ip -o -4 route show to default | awk '{print $5}' | head -n 1)
clang -O2 -g -Wall -target bpf -c /opt/xdp_quic_filter.c -o /opt/xdp_quic_filter.o
ip link set dev "$IFACE_EXT" xdp obj /opt/xdp_quic_filter.o sec xdp
```

### 0.3. MODOS DE FALLO Y RECUPERACIÓN

| Fallo | Detección | Acción automática | RPO/RTO |
|-------|-----------|-------------------|---------|
| Disco NVMe primario degradado | S.M.A.R.T. via `smartctl` cron cada 5min | Alerta Telegram. PostgreSQL replica a frío S3 (WAL-G). Failover manual a nodo secundario | RPO=0 (WAL). RTO<30min |
| Thermal runaway (>80°C) | RyzenAdj polling en systemd timer | RyzenAdj refuerza límite. Si persiste: shutdown ordenado de IA (Fase 2) primero, luego BBDD | RPO=0. RTO<5s (reinicio servicio IA) |
| ZFS pool corruption | `zpool scrub` semanal + `zfs list -t snapshot` | Rollback a último snapshot ZFS. Si irrecuperable: restauración WAL-G desde S3 | RPO=0 (snapshots horarios). RTO<1h |
| eBPF/XDP detach (driver update) | Systemd ExecStartPost con verificación `ip link show` | Re-inyección automática del programa XDP | RPO=N/A. RTO<1s |
| Bubblewrap escape (teórico) | Seccomp kill log en `dmesg` | El proceso atacante muere instantáneamente. Alert Telegram con stack trace | RPO=N/A. Impacto: nulo (sandbox efímero) |

### 0.4. VERIFICACIÓN

```bash
# 1. Confirmar aislamiento NUMA
numactl --hardware  # Debe mostrar 2 nodos (node 0: cores 0-15, node 1: cores 16-31)
cat /proc/cmdline   # Debe incluir isolcpus=0-15 nohz_full=0-15

# 2. Confirmar sello térmico
ryzenadj -i | grep "STAPM LIMIT"  # Debe ser 105000 (105W)
# Bajo carga: stress-ng -c 32 -t 30 && sensors | grep Tctl  # <80°C

# 3. Confirmar particionado
lsblk -f  # nvme0n1p1 sin FS, nvme0n1p2 = zfs, nvme1n1p1 = xfs
zfs get all pgpool | grep arc  # Verificar ARC max

# 4. Confirmar Jumbo Frames internos
ip link show "$IFACE_INT" | grep mtu  # Debe ser 9000

# 5. Confirmar XDP activo
ip link show "$IFACE_EXT" | grep xdp  # Debe mostrar "prog/xdp"

# 6. Confirmar Bubblewrap
echo '{"test": true}' | safe_json_parse.sh  # Debe devolver {"test":true}
echo '{"exploit": true}' | bwrap --unshare-all --new-session -- /bin/bash -c 'curl evil.com' 2>&1  # Debe fallar (red bloqueada)
```

[PROPUESTA DE MEJORA — Watchdog de Deriva Térmica]
**Problema:** RyzenAdj aplica límites una sola vez al boot. Si el firmware del SMC resetea los valores tras un evento ACPI (ej. suspensión momentánea por fallo eléctrico seguido de reconexión UPS), el PPT vuelve al default de 162W sin notificación.
**Implementación:** Crear un systemd timer que ejecute `ryzenadj -i` cada 60 segundos, parsee el PPT STAPM actual, y si difiere de 105000mW, lo reaplique y emita alerta.
**Impacto:** Eliminación del riesgo de drift térmico silencioso. Coste: ~0.001% CPU.
**Prerrequisitos:** RyzenAdj ya instalado (Paso 0.2.2).

```bash
cat << 'EOF' > /etc/systemd/system/cardex-thermal-watchdog.timer
[Unit]
Description=Thermal Drift Watchdog (60s interval)
[Timer]
OnBootSec=30
OnUnitActiveSec=60
[Install]
WantedBy=timers.target
EOF

cat << 'EOF' > /etc/systemd/system/cardex-thermal-watchdog.service
[Unit]
Description=Thermal Drift Check & Enforce
[Service]
Type=oneshot
ExecStart=/bin/bash -c 'CURRENT=$(ryzenadj -i 2>/dev/null | grep "STAPM LIMIT" | awk "{print \$NF}"); if [ "$CURRENT" != "105.000" ]; then ryzenadj --stapm-limit=105000 --fast-limit=105000 --slow-limit=105000 --tctl-temp=80; echo "[THERMAL DRIFT] Reapplied 105W lock. Was: $CURRENT" | logger -t cardex-thermal; fi'
EOF

systemctl daemon-reload && systemctl enable --now cardex-thermal-watchdog.timer
```

[PROPUESTA DE MEJORA — Cronometría PTP Híbrida]
**Problema:** V5 define un sistema PTP con hardware timestamping para coherencia de la base de datos, pero V6 lo omite. El NTP estándar tiene drift de 10-50ms, insuficiente para la secuenciación HFT donde dos eventos separados por <1ms deben ordenarse correctamente.
**Implementación:** Instalar `chrony` con `hwtimestamp` en la NIC, fallback a NTP Stratum 1 (Hetzner + PTB Alemania).
**Impacto:** Precisión de timestamping de ~1µs vs ~10ms. Crítico para el Global Sequence ID de la Fase 6.
**Prerrequisitos:** NIC con soporte de hardware timestamping (verificar con `ethtool -T $IFACE`).

```bash
apt-get install -y chrony
IFACE_EXT=$(ip -o -4 route show to default | awk '{print $5}')
cat << EOF > /etc/chrony/chrony.conf
hwtimestamp $IFACE_EXT
server ntp1.hetzner.de iburst xleave
server ptbtime1.ptb.de iburst xleave
makestep 1 3
rtcsync
EOF
systemctl restart chronyd
```

---

## FASE 1: BÓVEDA INMUTABLE, PERSISTENCIA POLÍGLOTA Y SOBERANÍA RGPD

### 1.0. QUÉ HACE

Establece la capa de datos dual: un motor transaccional ACID (PostgreSQL) para identidades B2B, suscripciones, fideicomisos y estado de subastas; y un motor analítico columnar (ClickHouse) para la telemetría de inventario continental (centenares de millones de registros vehiculares). Ambos motores se replican en tiempo real mediante Zero-ETL (MaterializedPostgreSQL) custodiado por un Schema Watchdog que previene el colapso de la suscripción lógica ante cambios DDL. Un KMS persistente (HashiCorp Vault con backend Raft sobre ZFS) gestiona el cifrado en vuelo y habilita la destrucción criptográfica O(1) para cumplir el Derecho al Olvido (Art. 17 RGPD) sin alterar backups fríos.

### 1.1. POR QUÉ ASÍ Y NO DE OTRA FORMA

**PostgreSQL + ClickHouse vs. Solución única:** Una base de datos relacional estándar colapsa en agregaciones analíticas sobre >100M de registros vehiculares (full table scan en row-store = O(n) con amplificación de I/O). ClickHouse resuelve agregaciones en columnar con compresión LZ4 en <50ms sobre miles de millones de filas. Pero ClickHouse carece de soporte ACID para transacciones concurrentes (Mutex del Dark Pool, balance de créditos). La arquitectura políglota asigna cada motor a su fortaleza: OLTP en PostgreSQL, OLAP en ClickHouse.

**UUIDv7 vs. UUIDv4:** UUIDv4 genera claves primarias con distribución aleatoria uniforme. Cada INSERT toca una página B-Tree distinta, causando Page Splits continuos y fragmentación del índice. Con 50.000 inserciones/hora, el índice se degrada en semanas. UUIDv7 (RFC 9562) codifica el timestamp Unix en los 48 bits más significativos, garantizando inserciones monótonas en el extremo derecho del árbol. Zero fragmentación. Zero VACUUM de emergencia por bloat.

**Vault con Raft persistente vs. tmpfs:** V4/V5 mencionaban Vault en tmpfs (RAM pura). Un reinicio eléctrico destruiría todas las llaves de cifrado, causando un blackout criptográfico total e irrecuperable. El backend Raft sobre ZFS persiste el keyring cifrado en disco. Auto-Unseal via AWS KMS permite que Vault se desbloquee automáticamente al arrancar sin intervención humana. La RAM se usa exclusivamente como caché de ejecución con `mlock` para prevenir swapping de material criptográfico.

### 1.2. IMPLEMENTACIÓN EXACTA

#### 1.2.1. PostgreSQL 16 — Core Transaccional OLTP

```bash
# Dataset ZFS dedicado con alineación atómica a 8K (tamaño de página de PG)
zfs create -o recordsize=8k -o primarycache=all -o atime=off -o logbias=throughput pgpool/postgres

# Instalación
apt-get update && apt-get install -y postgresql-16 postgresql-contrib-16 pgbouncer wal-g \
  postgresql-16-pgoutput inotify-tools jq

# Migración del datadir al volumen ZFS
systemctl stop postgresql
rsync -a /var/lib/postgresql/16/main/ /pgpool/postgres/
rm -rf /var/lib/postgresql/16/main
ln -s /pgpool/postgres /var/lib/postgresql/16/main
chown -R postgres:postgres /pgpool/postgres
```

Configuración HFT inyectada en `postgresql.conf`:

```ini
# === ZFS Optimization (Zero Double-Write) ===
# ZFS CoW previene torn pages nativamente → full_page_writes innecesario
full_page_writes = off
wal_init_zero = off
wal_recycle = off
wal_compression = lz4

# === RAM OLTP (32GB asignados a CCD0) ===
shared_buffers = 16GB
effective_cache_size = 48GB
work_mem = 64MB
maintenance_work_mem = 2GB
random_page_cost = 1.1    # NVMe: acceso aleatorio ≈ secuencial

# === Replicación Lógica (alimenta ClickHouse via Zero-ETL) ===
wal_level = logical
max_replication_slots = 10
max_wal_senders = 10

# === Anti-Bloat MVCC (Dark Pool genera alta tasa de UPDATE) ===
autovacuum = on
autovacuum_max_workers = 6
autovacuum_naptime = 10s
autovacuum_vacuum_scale_factor = 0.01      # Trigger VACUUM al 1% de cambios (default 20%)
autovacuum_analyze_scale_factor = 0.005    # Trigger ANALYZE al 0.5%

# === IPC Exclusivo (Zero TCP/IP interno) ===
listen_addresses = '127.0.0.1'
unix_socket_directories = '/var/run/postgresql'
```

Tablas volátiles del Dark Pool (alta tasa de UPDATE) se configuran con `FILLFACTOR = 70` para habilitar HOT Updates (Heap-Only Tuples): actualizaciones que no modifican columnas indexadas se resuelven dentro de la misma página de 8KB sin crear una nueva versión de fila en una página diferente.

Anclaje NUMA a CCD0:

```bash
mkdir -p /etc/systemd/system/postgresql@.service.d/
cat << 'EOF' > /etc/systemd/system/postgresql@.service.d/override.conf
[Service]
ExecStart=
ExecStart=/usr/bin/numactl -C 0-15 -l /usr/lib/postgresql/%i/bin/postgres \
  -D /pgpool/postgres -c config_file=/etc/postgresql/%i/main/postgresql.conf
EOF
systemctl daemon-reload && systemctl start postgresql
```

#### 1.2.2. PgBouncer — Multiplexador IPC (Transaction Pooling)

```ini
# /etc/pgbouncer/pgbouncer.ini
[databases]
cardex_db = host=/var/run/postgresql port=5432 dbname=cardex_db

[pgbouncer]
listen_addr = 127.0.0.1
listen_port = 6432
unix_socket_dir = /var/run/postgresql
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction          # Libera conexión al commit (no al disconnect)
max_client_conn = 10000          # Absorbe ráfagas del Gateway QUIC
default_pool_size = 100
reserve_pool_size = 50
```

`pool_mode = transaction` permite que 10.000 conexiones concurrentes del Gateway compartan 100 conexiones reales a PostgreSQL. Cada transacción obtiene una conexión, ejecuta, hace commit, y la devuelve al pool en <1ms.

#### 1.2.3. ClickHouse — Core Analítico OLAP

```bash
# Instalación desde repositorio oficial
apt-get install -y apt-transport-https ca-certificates dirmngr
GNUPGHOME=$(mktemp -d)
GNUPGHOME="$GNUPGHOME" gpg --no-default-keyring \
  --keyring /usr/share/keyrings/clickhouse-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys 8919F6BD2B48D754
echo "deb [signed-by=/usr/share/keyrings/clickhouse-keyring.gpg] \
  https://packages.clickhouse.com/deb stable main" > /etc/apt/sources.list.d/clickhouse.list
apt-get update && apt-get install -y clickhouse-server clickhouse-client
chown -R clickhouse:clickhouse /var/lib/clickhouse
```

Tuning HFT:

```xml
<!-- /etc/clickhouse-server/config.d/hft_tuning.xml -->
<clickhouse>
  <vfs>
    <!-- io_uring: Zero-copy I/O directo al NVMe sin syscall blocking -->
    <io_uring_enabled>1</io_uring_enabled>
  </vfs>
  <merge_tree>
    <!-- Wide parts a partir de 10MB (optimiza lecturas columnar) -->
    <min_bytes_for_wide_part>10485760</min_bytes_for_wide_part>
  </merge_tree>
  <!-- Puerto PG para MaterializedPostgreSQL -->
  <postgresql_port>5432</postgresql_port>
</clickhouse>
```

Motor de tabla principal: `ReplacingMergeTree` — append-only con deduplicación asíncrona por background merge. Zero bloqueos I/O por UPDATE/DELETE. Las fluctuaciones de precio se inyectan como nuevas filas; el merge posterior colapsa versiones obsoletas basándose en el timestamp PTP.

Anclaje NUMA a CCD0:

```bash
mkdir -p /etc/systemd/system/clickhouse-server.service.d/
cat << 'EOF' > /etc/systemd/system/clickhouse-server.service.d/override.conf
[Service]
ExecStart=
ExecStart=/usr/bin/numactl -C 0-15 -l /usr/bin/clickhouse-server \
  --config=/etc/clickhouse-server/config.xml
EOF
systemctl daemon-reload && systemctl enable --now clickhouse-server
```

#### 1.2.4. Schema Watchdog — Protección Zero-ETL

ClickHouse establece una suscripción lógica nativa (`MaterializedPostgreSQL`) al WAL de PostgreSQL. El motor experimental colapsa si PostgreSQL ejecuta DDL (ALTER TABLE, ADD COLUMN) mientras la suscripción está activa. El Watchdog monitoriza el catálogo cada 10 segundos:

```bash
cat << 'EOF' > /usr/local/bin/schema_watchdog.sh
#!/bin/bash
PG_CONN="dbname=cardex_db user=postgres host=/var/run/postgresql"
LAST_DDL_HASH=$(psql "$PG_CONN" -tAc \
  "SELECT md5(string_agg(column_name || data_type, '' ORDER BY column_name)) \
   FROM information_schema.columns WHERE table_schema='public';")

while true; do
  sleep 10
  CURR_DDL_HASH=$(psql "$PG_CONN" -tAc \
    "SELECT md5(string_agg(column_name || data_type, '' ORDER BY column_name)) \
     FROM information_schema.columns WHERE table_schema='public';")

  if [ "$CURR_DDL_HASH" != "$LAST_DDL_HASH" ] && [ -n "$CURR_DDL_HASH" ]; then
    echo "[SCHEMA WATCHDOG] DDL mutation detected. Rebuilding MaterializedPostgreSQL..."
    clickhouse-client --query="SYSTEM STOP REPLICATED SENDS"
    clickhouse-client --query="DETACH DATABASE pg_sync;"
    clickhouse-client --query="ATTACH DATABASE pg_sync ENGINE = \
      MaterializedPostgreSQL('127.0.0.1:5432', 'cardex_db', 'postgres', 'VAULT_INJECTED_PW');"
    clickhouse-client --query="SYSTEM START REPLICATED SENDS"
    LAST_DDL_HASH=$CURR_DDL_HASH
    echo "[SCHEMA WATCHDOG] Replication restored."
  fi
done
EOF
chmod +x /usr/local/bin/schema_watchdog.sh

cat << 'EOF' > /etc/systemd/system/schema-watchdog.service
[Unit]
Description=ClickHouse MaterializedPostgreSQL Schema Watchdog
After=postgresql.service clickhouse-server.service
[Service]
ExecStart=/usr/local/bin/schema_watchdog.sh
Restart=always
User=root
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now schema-watchdog
```

#### 1.2.5. HashiCorp Vault — KMS Persistente y Crypto-Shredding RGPD

```bash
wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor > /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
  https://apt.releases.hashicorp.com bookworm main" > /etc/apt/sources.list.d/hashicorp.list
apt-get update && apt-get install -y vault awscli

# Dataset ZFS dedicado para el backend Raft
zfs create -o recordsize=128k -o compression=lz4 pgpool/vault_data
mkdir -p /pgpool/vault_data && chown -R vault:vault /pgpool/vault_data
```

```hcl
# /etc/vault.d/vault.hcl
storage "raft" {
  path    = "/pgpool/vault_data"
  node_id = "cardex_kms_node_01"
}

listener "tcp" {
  address     = "127.0.0.1:8200"
  tls_disable = 1                   # TLS innecesario en loopback
}

# Bloqueo en RAM: las DEKs descifradas jamás se escriben al swap
disable_mlock = false

# Auto-Unseal: Vault se desbloquea automáticamente al arrancar
# usando la KMS key de AWS como Root of Trust
seal "awskms" {
  region     = "eu-central-1"
  kms_key_id = "alias/cardex-vault-auto-unseal"
}

ui = false  # Zero superficie de ataque web
```

**Flujo de Crypto-Shredding (Art. 17 RGPD):**

1. Cada entidad B2B se asocia a una Data Encryption Key (DEK) única en Vault (motor `Transit`).
2. Todo PII (teléfonos, contratos, emails) se cifra en RAM con AES-256-GCM antes de escribirse a PostgreSQL. El IV (Initialization Vector) es dinámico por operación.
3. Para ejecutar el Derecho al Olvido: `vault write transit/keys/entity_<ULID>/config deletion_allowed=true` seguido de `vault delete transit/keys/entity_<ULID>`. Tiempo de ejecución: O(1) — independiente del volumen de datos.
4. Todo backup frío (WAL-G en S3, snapshots ZFS) que contenga registros de esa entidad sufre un colapso criptográfico permanente e irreversible: los datos persisten como ciphertext irrecuperable sin la DEK destruida.

Backup del keyring (S3 Glacier, cron cada 6h):

```bash
cat << 'EOF' > /usr/local/bin/vault_s3_backup.sh
#!/bin/bash
export VAULT_ADDR='http://127.0.0.1:8200'
export VAULT_TOKEN=$(cat /etc/vault.d/.root_token)
BACKUP_PATH="/tmp/vault_raft_$(date +%s).snap"
vault operator raft snapshot save "$BACKUP_PATH"
aws s3 cp "$BACKUP_PATH" s3://cardex-cold-backups/vault-keys/ --storage-class GLACIER
rm -f "$BACKUP_PATH"
EOF
chmod +x /usr/local/bin/vault_s3_backup.sh
echo "0 */6 * * * root /usr/local/bin/vault_s3_backup.sh > /dev/null 2>&1" > /etc/cron.d/vault_snapshot
```

#### 1.2.6. WAL-G — Continuous Archiving (PITR)

```bash
mkdir -p /etc/wal-g.d/env
echo "s3://cardex-cold-backups/pg-wal/" > /etc/wal-g.d/env/WALG_S3_PREFIX
echo "eu-central-1" > /etc/wal-g.d/env/AWS_REGION
echo "lz4" > /etc/wal-g.d/env/WALG_COMPRESSION_METHOD
chown -R postgres:postgres /etc/wal-g.d

# Habilitar en PostgreSQL
cat << 'EOF' >> /etc/postgresql/16/main/postgresql.conf
archive_mode = on
archive_command = 'envdir /etc/wal-g.d/env wal-g wal-push %p'
archive_timeout = 60s
EOF
systemctl restart postgresql
```

### 1.3. MODOS DE FALLO Y RECUPERACIÓN

| Fallo | Detección | Acción | RPO/RTO |
|-------|-----------|--------|---------|
| PostgreSQL crash | systemd Restart=always + pg_isready cron | Restart automático. Recuperación WAL nativa | RPO=0. RTO<5s |
| ClickHouse desync (DDL drift) | Schema Watchdog detecta hash mismatch | Detach + Reattach MaterializedPostgreSQL | RPO=0 (WAL preservado). RTO<30s |
| Vault sealed post-reinicio | Auto-Unseal via AWS KMS | Unsealing automático en <5s. Fallback: manual unseal con Shamir keys | RPO=0. RTO<10s |
| AWS KMS inaccesible | Vault health check + retry exponencial | Vault permanece sealed. Alertas. Datos cifrados inaccesibles temporalmente. PG/CH operan con datos no-PII sin interrumpir | RPO=0. RTO=duración del outage de AWS |
| Corrupción de backup S3 | Checksum SHA-256 en cada upload + `aws s3api head-object` validación | Re-upload desde snapshot ZFS local | RPO=0 (múltiples copias). RTO<10min |

### 1.4. VERIFICACIÓN

```bash
# PostgreSQL
psql -h /var/run/postgresql -U postgres -c "SELECT version();"  # PG 16.x
psql -c "SHOW full_page_writes;"  # off
psql -c "SHOW wal_level;"  # logical

# ClickHouse
clickhouse-client --query="SELECT version();"
clickhouse-client --query="SHOW DATABASES;" | grep pg_sync  # Debe existir

# Vault
export VAULT_ADDR='http://127.0.0.1:8200'
vault status  # Sealed: false, HA Enabled: false

# Schema Watchdog
systemctl status schema-watchdog  # active (running)

# Zero-ETL (insertar en PG, verificar en CH)
psql -c "INSERT INTO test_replication (id, val) VALUES (gen_random_uuid(), 'test');"
sleep 5
clickhouse-client --query="SELECT count() FROM pg_sync.test_replication;"  # >0
```

[PROPUESTA DE MEJORA — ClickHouse Zero-PII Enforcement]
**Problema:** V5/V6 declaran que ClickHouse no debe contener PII. Pero la replicación MaterializedPostgreSQL copia TODAS las columnas, incluyendo campos cifrados.
**Implementación:** Crear una vista materializada en PostgreSQL que exponga solo columnas no-PII (entity_ulid, pricing, mileage, timestamps) y configurar MaterializedPostgreSQL para replicar esa vista, no las tablas base.
**Impacto:** Eliminación estructural (no solo política) de PII en ClickHouse. Simplifica auditorías RGPD.
**Prerrequisitos:** PostgreSQL `CREATE PUBLICATION` sobre la vista filtrada.

---

## FASE 2: MOTOR NEURONAL PROBABILÍSTICO (SCORING AI & FAIL-CLOSED)

### 2.0. QUÉ HACE

Despliega un motor de inferencia local (zero-cloud) basado en llama.cpp compilado sin AVX-512, que opera como perito matemático probabilístico — no como oráculo infalible. Extrae datos estructurados de texto no estructurado (descripciones de anuncios en 12+ idiomas), puntúa su confianza, y deriva a auditoría humana cualquier resultado con certeza <95%. Ubicación: Nodo 03, CCD1 (cores 16-31).

### 2.1. POR QUÉ ASÍ Y NO DE OTRA FORMA

**AVX-512 purge vs. AVX-512 nativo:** El AMD Zen 4 implementa AVX-512 como "double-pumped" — usa las unidades AVX2 de 256 bits ejecutando dos micro-ops por instrucción de 512 bits. Bajo carga sostenida (24/7), esto provoca un incremento térmico de ~15W que, combinado con el PPT de 105W, reduce la frecuencia disponible para el resto de operaciones. El throughput neto en inferencia GGUF Q5_K_M mejora solo ~8% con AVX-512 vs. AVX2+VNNI, pero el coste en estabilidad térmica y determinismo no lo justifica. Compilar con `-mno-avx512f` es la decisión correcta para un sistema que prioriza latencia predecible sobre throughput pico.

**Confianza explícita vs. output binario:** V1-V3 trataban los outputs de IA como verdades absolutas. Un error en la clasificación fiscal (ej. declarar deducible un vehículo con régimen de margen) genera responsabilidad civil directa. El modelo probabilístico fuerza al LLM a emitir un float `confidence` entre 0.0 y 1.0 mediante gramática GBNF. Cualquier valor <0.95 se marca como `REQUIRES_HUMAN_AUDIT` y se bloquea la automatización fiduciaria hasta revisión manual.

**GBNF anti-injection vs. post-procesado regex:** Un LLM sin restricciones de output puede generar JSON malformado, inyectar prompts en campos de texto, o producir valores fuera de rango. La gramática GBNF opera a nivel de decodificación: durante el sampling, cualquier token que violaría la gramática recibe probabilidad -∞ antes de la softmax. El ataque muere en la ALU, no en una validación posterior.

### 2.2. IMPLEMENTACIÓN EXACTA

#### 2.2.1. Compilación llama.cpp (Zero-AVX512)

```bash
apt-get update && apt-get install -y cmake build-essential numactl python3-pip git wget curl jq bc
git clone https://github.com/ggerganov/llama.cpp.git /opt/llama.cpp
cd /opt/llama.cpp

cmake -B build \
  -DGGML_AVX512=OFF -DGGML_AVX512_VBMI=OFF -DGGML_AVX512_VNNI=OFF \
  -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_OPENMP=ON \
  -DCMAKE_CXX_FLAGS="-march=znver4 -mno-avx512f -mno-avx512vl -mno-avx512bw -mno-avx512dq -mno-avx512cd -O3" \
  -DCMAKE_C_FLAGS="-march=znver4 -mno-avx512f -mno-avx512vl -mno-avx512bw -mno-avx512dq -mno-avx512cd -O3"

cmake --build build --config Release -j 16
cp build/bin/llama-server /usr/local/bin/
```

#### 2.2.2. Modelos y Gramática

```bash
mkdir -p /opt/models/gguf /opt/grammars

# Qwen2.5-Coder-7B (L3 extractor generalista, Q5_K_M, ~6GB RAM)
pip3 install huggingface-hub --break-system-packages
huggingface-cli download Qwen/Qwen2.5-Coder-7B-Instruct-GGUF \
  qwen2.5-coder-7b-instruct-q5_k_m.gguf --local-dir /opt/models/gguf

# Nomic-embed-text-v1.5 (L2 vectorización, 768 dims, <2ms)
huggingface-cli download nomic-ai/nomic-embed-text-v1.5-GGUF \
  nomic-embed-text-v1.5.Q8_0.gguf --local-dir /opt/models/gguf
```

Gramática GBNF con scoring obligatorio:

```bash
cat << 'EOF' > /opt/grammars/institutional_scoring.gbnf
root ::= "{" ws "\"tax_status\"" ws ":" ws status_enum "," ws "\"confidence\"" ws ":" ws number "}"
ws ::= [ \t\n]*
status_enum ::= "\"DEDUCTIBLE\"" | "\"REBU\"" | "\"UNKNOWN\""
number ::= "0." [0-9]+ | "1.0"
EOF
```

#### 2.2.3. Cascade L1/L2/L3 (Inversión Térmica)

El sistema implementa tres capas de resolución con carga computacional decreciente según uso:

| Capa | Mecanismo | Latencia | CPU | Cuándo se invoca |
|------|-----------|----------|-----|------------------|
| L1 | Redis HGET exact match (`dict:l1_tax`) | 0.001ms | 0% | Siempre (primera consulta) |
| L2 | HNSW vector search (Nomic embeddings en Redis) | <2ms | <1% | Si L1 miss |
| L3 | Qwen2.5-7B con GBNF grammar (async via Redis Streams) | <3s | ~50% de 8 cores | Si L2 miss. Resultados se inyectan en L1/L2 |

La carga computacional es inversamente proporcional al tiempo: al inicio (cold start), el 100% de los vehículos pasan por L3. Conforme el diccionario L1 crece, L3 se invoca logarítmicamente menos. A escala continental estable, >95% de las consultas se resuelven en L1 (0.001ms).

#### 2.2.4. Servicio L3 (Qwen2.5) y Worker IPC

```bash
# Demonio L3 anclado a cores 16-23
cat << 'EOF' > /etc/systemd/system/ia-l3-qwen.service
[Unit]
Description=L3 IA Generativa (Qwen2.5) AVX2+VNNI
After=network.target
[Service]
ExecStart=/usr/bin/numactl -C 16-23 -l /usr/local/bin/llama-server \
  -m /opt/models/gguf/qwen2.5-coder-7b-instruct-q5_k_m.gguf \
  --host 127.0.0.1 --port 8081 \
  --threads 8 -c 8192 -b 512 --parallel 8 --cont-batching --mlock
Restart=always
User=root
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now ia-l3-qwen
```

Worker IPC probabilístico (cores 30-31):

```bash
cat << 'EOF' > /usr/local/bin/l3_probabilistic_worker.sh
#!/bin/bash
set -euo pipefail
REDIS_CLI="redis-cli -h 10.0.0.1"

while true; do
  OUTPUT=$($REDIS_CLI --raw XREADGROUP GROUP cg_qwen_workers worker1 \
    COUNT 1 BLOCK 5000 STREAMS stream:l3_pending > 2>/dev/null || true)
  if [[ -z "$OUTPUT" ]]; then continue; fi

  mapfile -t LINES <<< "$OUTPUT"
  ID="${LINES[1]:-}"
  RAW_TEXT="${LINES[3]:-}"

  if [[ -n "$ID" && -n "$RAW_TEXT" ]]; then
    export RAW_TEXT
    PAYLOAD=$(jq -n -c \
      --arg prefix "Evalúa el estado fiscal basándote en la descripción. Emite tax_status y confidence (0.0 a 1.0): " \
      '{
        "prompt": ($prefix + env.RAW_TEXT),
        "grammar_file": "/opt/grammars/institutional_scoring.gbnf",
        "temperature": 0.0,
        "n_predict": 64
      }')

    RESPONSE=$(curl -s -X POST http://127.0.0.1:8081/completion \
      -H "Content-Type: application/json" -d "$PAYLOAD")
    JSON_OUT=$(printf "%s" "$RESPONSE" | jq -c -r '.content // empty')

    if [[ -n "$JSON_OUT" ]]; then
      CONFIDENCE=$(echo "$JSON_OUT" | jq -r '.confidence')
      STATUS=$(echo "$JSON_OUT" | jq -r '.tax_status')

      # FAIL-CLOSED INSTITUCIONAL: < 95% = derivación a auditoría humana
      if (( $(echo "$CONFIDENCE < 0.95" | bc -l) )); then
        STATUS="REQUIRES_HUMAN_AUDIT"
      fi

      printf "%s" "{\"tax_status\": \"$STATUS\", \"confidence\": $CONFIDENCE}" | \
        $REDIS_CLI -x HSET "dict:l1_tax" "$ID" > /dev/null
    fi

    $REDIS_CLI XACK stream:l3_pending cg_qwen_workers "$ID" > /dev/null
  fi
done
EOF
chmod +x /usr/local/bin/l3_probabilistic_worker.sh
```

### 2.3. MODOS DE FALLO

| Fallo | Acción | Impacto |
|-------|--------|---------|
| llama-server OOM (modelo >128GB RAM disponible) | mlock previene paginación. Si RAM insuficiente: servicio no arranca, alerta | L3 offline. L1/L2 siguen operando. Vehículos nuevos se marcan REQUIRES_HUMAN_AUDIT |
| GBNF grammar error (output inválido) | llama.cpp retorna error de parsing. Worker lo descarta | Vehículo se marca UNKNOWN. Auditoría humana |
| Thermal throttling (si RyzenAdj falla) | Watchdog de Fase 0 reaplica PPT | Latencia L3 se degrada temporalmente. Sin pérdida de datos |

---

## FASE 3: META-INDEXACIÓN INSTITUCIONAL (WHITE-HAT ACQUISITION)

### 3.0. QUÉ HACE

Gateway bifronte que ingiere mercado desde dos canales exclusivamente legales: (1) webhooks B2B autenticados por HMAC desde flotas y casas de subasta licenciadas (Arval, BCA, LeasePlan); (2) telemetría Edge delegada al hardware del cliente (EU Data Act) transmitida por QUIC/UDP con firma Ed25519 anti-poisoning. Ubicación: Nodo 02.

### 3.1. POR QUÉ ASÍ Y NO DE OTRA FORMA

**Webhooks B2B vs. Scraping:** El scraping de portales genera tres categorías de riesgo: penal (Art. 197 CP español, CFAA estadounidense), civil (incumplimiento de ToS) y operativo (guerra de WAFs que consume OPEX sin generar valor). Los webhooks B2B invierten la relación: el proveedor empuja datos hacia CARDEX bajo contrato de licencia. Coste marginal por vehículo: ~0€. Uptime: 99.9% (vs. ~85% del scraping sujeto a rate limits y captchas).

**Extracción Edge (EU Data Act):** Para portales sin acuerdo B2B (Mobile.de, AutoScout24), la extracción la ejecuta el Caballo de Troya (Fase 9) instalado en el ordenador del concesionario cliente. El concesionario está amparado por el Derecho de Acceso del EU Data Act para acceder a datos de plataformas donde opera con su propia IP residencial.

**Ed25519 vs. HMAC para Edge:** El canal QUIC está expuesto a Internet. Un competidor podría inyectar 100.000 vehículos ficticios a 1€ para destruir los algoritmos de pricing. Ed25519 (firma asimétrica) permite verificar la autenticidad del emisor sin compartir la clave privada con los nodos Edge. Verificación: O(1) en ~50µs. Si la firma es inválida, el datagrama UDP se destruye en RAM sin procesamiento.

### 3.2. IMPLEMENTACIÓN EXACTA

#### 3.2.1. Gateway Go Bifronte (QUIC + Webhooks HTTPS)

El código completo del gateway se despliega en Nodo 02. Implementa:

- **Canal 1 (TCP:8080):** Endpoint `/api/v2/webhook/b2b` con validación HMAC-SHA256 en header `X-Cardex-Signature`. Todo payload válido se inyecta en `stream:ingestion_raw`.
- **Canal 2 (UDP:4433):** Listener QUIC con TLS 1.3 y Allow0RTT. Cada `EdgePayload` contiene `{sig, ts, data}`. Anti-replay: ventana de 60s sobre timestamp. Firma Ed25519 verificada antes de cualquier procesamiento.

```bash
# Compilación y despliegue
cd /opt/cardex-gateway-v2
go build -ldflags="-s -w" -o gateway-v2 main.go

cat << 'EOF' > /etc/systemd/system/cardex-gateway-v2.service
[Unit]
Description=Institutional Gateway V2 (B2B Webhooks & Edge QUIC)
After=network.target
[Service]
ExecStart=/usr/bin/numactl -C 16-31 /opt/cardex-gateway-v2/gateway-v2
WorkingDirectory=/opt/cardex-gateway-v2
Restart=always
LimitNOFILE=5000000
User=root
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now cardex-gateway-v2
```

#### 3.2.2. Token Bucket Rate Limiter

Para portales B2B con límites volumétricos contractuales, se implementa un rate limiter atómico en Redis Lua:

```lua
-- KEYS[1] = "ratelimit:<source_id>"
-- ARGV[1] = max_tokens, ARGV[2] = refill_rate_per_sec, ARGV[3] = now_ms
local tokens = tonumber(redis.call("GET", KEYS[1]) or ARGV[1])
local last = tonumber(redis.call("GET", KEYS[1]..":ts") or ARGV[3])
local elapsed = (tonumber(ARGV[3]) - last) / 1000
tokens = math.min(tonumber(ARGV[1]), tokens + elapsed * tonumber(ARGV[2]))
if tokens >= 1 then
  redis.call("SET", KEYS[1], tokens - 1)
  redis.call("SET", KEYS[1]..":ts", ARGV[3])
  return 1  -- PERMIT
else
  return 0  -- DENY (respeta Retry-After del portal)
end
```

---

## FASE 4: PIPELINE HFT Y SHARDING ESPACIAL

### 4.0. QUÉ HACE

Procesa la telemetría bruta de la Fase 3 a velocidad HFT: deduplica vehículos en O(1) mediante Bloom Filters, asigna shards geoespaciales hexagonales (Uber H3, resolución 4), calcula el Gross Physical Cost en EUR con fail-closed absoluto ante divisas desconocidas, y enruta los activos validados hacia las fases forense (5) y financiera (6). Ubicación: Nodo 02, cores 0-7.

### 4.1. COMPONENTES CRÍTICOS

**RedisBloom (O(1) deduplication):** Huella SHA-256 de `VIN + color_lowercase + mileage`. Comprobación contra `BF.ADD bloom:vehicles`. Si ya existe: descarte inmediato sin acceso a disco. False positive rate: configurable (default 0.01%). Capacidad: 50M entries a ~60MB de RAM.

**Uber H3 (Hexagonal Sharding):** Coordenadas GPS → índice hexagonal H3 a resolución 4 (~1.700 km² por hexágono). Permite agrupar oferta/demanda por proximidad geográfica como simple string match. Resolución fractal: se puede refinar a res. 7 (~5.16 km²) para análisis local sin reindexación.

**Banker's Buffer (Fail-Closed FX):** Redis hash `fx_buffer` contiene multiplicadores EUR validados cada hora. Si una divisa no existe en el oráculo: el vehículo se destruye atómicamente (`FATAL_CURRENCY_FAIL`). Zero asunciones. El buffer incluye un 2% de safety cushion para absorber volatilidad intradía.

**Semantic Kill-Switch:** Vehículos con precio <1.000€ o >500.000€ se descartan como outliers/typos antes del procesamiento fiscal.

**Backpressure:** Si `stream:db_write` supera 50.000 mensajes pendientes, los workers de pipeline pausan la ingesta para prevenir OOM en las fases downstream.

### 4.2. DESPLIEGUE

```bash
cd /opt/cardex-pipeline-v2
go build -ldflags="-s -w" -o pipeline-worker pipeline.go

cat << 'EOF' > /etc/systemd/system/cardex-pipeline-v2.service
[Unit]
Description=Cardex Phase 4 (HFT Pipeline & Spatial Sharding)
After=network.target redis-server.service
[Service]
ExecStart=/usr/bin/numactl -C 0-7 /opt/cardex-pipeline-v2/pipeline-worker
WorkingDirectory=/opt/cardex-pipeline-v2
Restart=always
User=root
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now cardex-pipeline-v2
```

---

## FASE 5: CRISOL FORENSE Y FISCALIDAD CONDICIONADA

### 5.0. QUÉ HACE

Purificación determinista del activo vehicular: (1) Tax Hunter que combina detección sintáctica (Aho-Corasick) con scoring probabilístico (L3 Qwen2.5) para clasificar deducibilidad IVA; (2) triangulación VIES asíncrona con circuit breaker optimista (120s timeout); (3) cascade OCR termomoderado (RapidOCR ONNX, singleton, 2 threads máximo) para extracción de VIN desde imágenes. Ubicación: Nodo 03, cores 24-31.

### 5.1. FLUJO DE CLASIFICACIÓN FISCAL

```
Vehículo entrante
    │
    ├─→ Aho-Corasick scan (Determinista)
    │     Busca: "§25a", "ustg", "margeregeling", "mwst nicht ausweisbar", "rebu", "margen"
    │     Si match → TaxStatus = REBU (override incondicional)
    │
    ├─→ Si no match → Consultar L1 cache (dict:l1_tax)
    │     Si hit Y confidence ≥ 0.95 → TaxStatus = valor cacheado
    │     Si hit Y confidence < 0.95 → TaxStatus = REQUIRES_HUMAN_AUDIT
    │
    ├─→ Si L1 miss → Derivar a L3 async (stream:l3_pending)
    │     Resultado futuro se inyecta en L1 para consultas subsiguientes
    │
    └─→ Si Seller es B2B con VAT_ID → VIES triangulation
          Si VIES responde valid → DEDUCTIBLE
          Si VIES responde invalid → REBU
          Si VIES timeout (>200ms) → PENDING_VIES_OPTIMISTIC
            (El vehículo entra al mercado pero el pago se bloquea
             hasta reconciliación background)
```

**Entity-Type Hard Override:** Si `Seller_Type == PRIVATE`, el TaxStatus se fuerza a REBU independientemente de cualquier otro resultado. Un particular no puede emitir factura con IVA deducible bajo ninguna circunstancia en la UE.

### 5.2. OCR Termomoderado

```python
# Blindaje termodinámico innegociable
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"

# Singleton: una sola instancia ONNX en RAM
ocr_engine = RapidOCR()

# VIN regex ISO 3779: 17 caracteres, excluye I/O/Q
VIN_REGEX = re.compile(r'\b[A-HJ-NPR-Z0-9]{17}\b')
```

Sin el throttle a 2 threads, 500 fotos simultáneas levantan 8.000 threads ONNX que colapsan el kernel por Thread Thrashing (context switch overhead > compute time).

### 5.3. DESPLIEGUE

```bash
cd /opt/cardex-forensics-v2
python3 -m venv venv
./venv/bin/pip install redis orjson pyahocorasick rapidocr-onnxruntime numpy opencv-python-headless aiohttp uvloop

# Tax Hunter
cat << 'EOF' > /etc/systemd/system/cardex-tax-hunter-v2.service
[Unit]
Description=Cardex Phase 5: Tax Hunter (Aho-Corasick + VIES + L3)
After=network.target redis-server.service ia-l3-qwen.service
[Service]
ExecStart=/usr/bin/numactl -C 24-31 /opt/cardex-forensics-v2/venv/bin/python \
  /opt/cardex-forensics-v2/tax_hunter.py
Restart=always
User=root
[Install]
WantedBy=multi-user.target
EOF

# Cascade OCR
cat << 'EOF' > /etc/systemd/system/cardex-cascade-ocr-v2.service
[Unit]
Description=Cardex Phase 5: Cascade OCR (ONNX Singleton, 2 threads)
After=network.target
[Service]
ExecStart=/usr/bin/numactl -C 24-31 /opt/cardex-forensics-v2/venv/bin/python \
  /opt/cardex-forensics-v2/cascade_ocr.py
Restart=always
User=root
[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now cardex-tax-hunter-v2 cardex-cascade-ocr-v2
```

---

## FASE 6: MOTOR FINANCIERO Y RADAR HFT (ALPHA ENGINE)

### 6.0. QUÉ HACE

Calcula el Net Landed Cost (NLC) transfronterizo en <50ms combinando: Gross Physical Cost (Fase 4) + impuestos soberanos nacionales en RAM + logística pessimista (worst-case con timeout de 50ms). Firma cada cotización con HMAC-SHA256 para prevenir race conditions entre mutación de precio y ejecución de compra. Infiere desesperación del vendedor (SDI) detectando curtailment cliffs de financiación. Distribuye el mercado via QUIC HTTP/3 con SSE fan-out. Ubicación: Nodo 04.

### 6.1. FÓRMULAS FISCALES SOBERANAS

```
NLC = GrossPhysicalCost + Logistics(worst_case) + Taxes(target_market)
```

| País destino | Impuesto | Fórmula |
|-------------|----------|---------|
| España (ES) | IEDMT | CO₂ ≥ 200 → 14.75%; CO₂ ≥ 160 → 9.75%; CO₂ ≥ 120 → 4.75%; <120 → 0% |
| Francia (FR) | Malus Écologique | `malus = min((CO₂ - 117)² × 10, 60000) × (1 - age_years × 0.10)`. Si CO₂ ≤ 117 → 0€ |
| Países Bajos (NL) | Rest-BPM | `base = CO₂ × 130€`, depreciación forfaitaria: `base × (1 - min(age_months × 0.01, 0.90))` |

**Si `TaxStatus == REBU`:** Taxes = 0€ (IVA incluido en el margen comercial del vendedor).

### 6.2. HMAC Quote System (Zero Race-Condition)

```go
func generateQuoteID(hash string, price float64) string {
    payload := fmt.Sprintf("%s|%.2f|%d", hash, price, time.Now().UnixNano())
    h := hmac.New(sha256.New, []byte(secretKey))
    h.Write([]byte(payload))
    return hex.EncodeToString(h.Sum(nil))
}
```

Cuando el cliente pulsa "Reservar", debe enviar el `quote_id` recibido. El Lua Mutex (Fase 6.3) verifica atómicamente que el quote no haya mutado. Si el precio cambió en tránsito: `PRICE_MISMATCH (-2)` → el cliente debe refrescar la cotización.

### 6.3. Redis Lua Mutex Atómico

```lua
-- KEYS[1] = "lock:<vehicle_hash>"
-- KEYS[2] = "vehicle_state:<vehicle_hash>"
-- ARGV[1] = buyer_id, ARGV[2] = quote_id_hmac
if redis.call("EXISTS", KEYS[1]) == 1 then
  return -1  -- SOLD_OUT
end
local current_quote = redis.call("HGET", KEYS[2], "quote_id")
if current_quote and current_quote ~= ARGV[2] then
  return -2  -- PRICE_MISMATCH
end
redis.call("SET", KEYS[1], ARGV[1], "EX", 120)  -- Lock 120s
return 1     -- LOCKED_SUCCESS
```

Redis es single-threaded: 500 pujas concurrentes sobre el mismo vehículo se serializan en O(1). El primero gana. Los 499 restantes reciben respuesta síncrona en <1ms.

### 6.4. Seller Desperation Index (SDI)

```go
isDesperate := (v.DaysOnMarket >= 58 && v.DaysOnMarket <= 65) ||
               (v.DaysOnMarket >= 88 && v.DaysOnMarket <= 95)
```

Los umbrales 60/90 días corresponden a los ciclos de amortización estándar del Floorplan Financing europeo. A los 60 días, el concesionario paga el primer tramo de intereses. A los 90, la financiera puede ejecutar la cláusula de recompra. El SDI flag habilita ofertas agresivas justificadas matemáticamente.

---

## FASE 7: ARQUEOLOGÍA JURÍDICA E HISTÓRICO B2B (LICENSED FORENSICS)

### 7.0. QUÉ HACE

Hub institucional que ejecuta tres funciones: (1) detección de odometer rollback cruzando kilometrajes históricos en ClickHouse O(1) con tolerancia logística de 500km; (2) consulta legal a APIs B2B oficiales de pago (IDEAUTO, CARFAX) con timeout estricto de 120s para verificar cargas/embargos; (3) gestión del risk delegation cuando las APIs colapsan (flag `LEGAL_TIMEOUT` + waiver obligatorio al comprador). Ubicación: Nodo 05.

### 7.1. FLUJO DE VERIFICACIÓN LEGAL

```
Reserva confirmada (Mutex = 1)
    │
    ├─→ ClickHouse: SELECT max(mileage) FROM mileage_history WHERE vin=? AND mileage > current+500
    │     Si existe → FRAUD_ODOMETER_ROLLBACK (bloqueo absoluto)
    │
    ├─→ API B2B oficial (IDEAUTO/CARFAX): GET /check_vin?vin=<VIN>
    │     Timeout: 120s (anti-thread-starvation)
    │     200 OK → LEGAL_CLEAR
    │     403/404 → LEGAL_LIEN_OR_STOLEN (bloqueo absoluto)
    │     Timeout → LEGAL_TIMEOUT
    │
    └─→ Si LEGAL_TIMEOUT:
          Vehículo publicado con flag LEGAL_UNKNOWN
          Compra permitida SOLO con firma de Waiver por el comprador
          Background sweep reintenta cada 30min hasta resolución
```

**OPEX como seguro legal:** La consulta B2B cuesta 1-3€ por VIN. Se ejecuta SOLO en el momento de la reserva, no durante la ingesta de millones de vehículos. Coste proyectado: ~0.15€ por vehículo que llega a fase de reserva.

---

## FASE 8: TERMINAL Y DARK POOL (PRODUCTO B2B INSTITUCIONAL)

### 8.0. QUÉ HACE

Interfaz de trading B2B con tres componentes: (1) motor HFT en Rust→WASM ejecutado en Web Worker (zero main-thread blocking, 120 FPS, virtual scroller de 30 nodos DOM reciclados infinitamente); (2) sistema de Karma Slashing reputacional (no financiero) que penaliza especuladores con latencia artificial (+500ms) en lugar de cargos bancarios; (3) gateway SIP legal para llamadas B2B via Twilio DIDs con compliance STIR/SHAKEN. Ubicación: Nodo 06 (backend), cliente (WASM).

### 8.1. DECISIONES DE DISEÑO

**Virtual Scroller vs. DOM completo:** Renderizar 100.000 tarjetas de vehículo destruye el navegador (>2GB DOM heap). El WASM ordena el inventario por NLC en silicio y envía exclusivamente un JSON con los 30 elementos visibles en el viewport. JavaScript recicla 30 nodos HTML infinitamente. El usuario puede hacer Ctrl+C (a diferencia del Canvas rendering que destruye la accesibilidad).

**Karma vs. Slashing financiero:** V4 proponía deducir saldo real por reservas expiradas. Esto genera chargebacks en Stripe y litigios. El Karma es un token reputacional: expira reserva sin compra → -15 karma. Si karma < 50 → shadow ban (+500ms latencia inyectada por el gateway QUIC). El operador ve el mercado medio segundo tarde, perdiendo sistemáticamente los mejores deals. Educación por consecuencia competitiva, no por extracción financiera.

### 8.2. COMPONENTES CLAVE

Motor WASM (Rust):
```rust
#[wasm_bindgen]
pub fn render_viewport(&self, offset: usize, limit: usize) -> String {
    let mut active: Vec<&Vehicle> = self.inventory.values().collect();
    active.sort_by(|a, b| a.nlc.partial_cmp(&b.nlc).unwrap_or(std::cmp::Ordering::Equal));
    let paginated: Vec<&Vehicle> = active.into_iter().skip(offset).take(limit).collect();
    serde_json::to_string(&paginated).unwrap_or_else(|_| "[]".to_string())
}
```

SIP Gateway (Twilio): DIDs legales alquilados bajo KYC corporativo de CARDEX OPS AG. Enrutamiento por país del vendedor. Compliance EU Telecom Act + STIR/SHAKEN.

---

## FASE 9: CABALLO DE TROYA B2B (DMS EDGE DEPLOYMENT)

### 9.0. QUÉ HACE

Aplicación desktop Tauri/Rust instalada en los PCs de los concesionarios clientes que opera como nodo extractor delegado bajo amparo del EU Data Act. Tres funciones: (1) extracción silenciosa de portales via Ghost WebViews nativos (Edge WebView2/WKWebView) invisibles para EDR; (2) OCR local en WASM (fotos procesadas y destruidas antes de transmitir texto); (3) Passive QoS que monitoriza RTT del socket y pausa la cola si detecta congestión para no interferir con el negocio del cliente.

### 9.1. IMPLEMENTACIÓN

**EV Code Signing (400€/año):** Certificado Extended Validation con token USB HSM. Windows SmartScreen otorga inmunidad al instalador. Sin este certificado, el binario se bloquea al primer intento de ejecución.

**Ghost WebViews:** Instancia `WindowBuilder` con `visible(false)` y `decorations(false)`. Para el antivirus corporativo, el tráfico web es 100% nativo del SO — indistinguible de un usuario navegando.

**Cloudflare for SaaS:** Cada cliente recibe su TLD personalizado (`.com`/`.es`) via CNAME flattening con auto TLS. JSON-LD `schema.org/Vehicle` con `isPartOf` (no `rel="sponsored"`) para absorción de PageRank limpia.

**Passive TCP Backpressure:** Primera foto comprimida a WebP/AVIF en origen (85% reducción). RTT medido pasivamente. Si >500ms: pausa dinámica de la cola. Zero interferencia con datáfonos y POS del concesionario.

---

## FASE 10: INGENIERÍA CORPORATIVA, CAPITAL Y WAR ROOM LEGAL

### 10.0. QUÉ HACE

Estructura legal y financiera del entramado corporativo: (1) CARDEX OPS AG (Suiza) como holding de IP y sede de algoritmos — subsidiaria UE como agencia cost-plus al 5%; (2) evasión MiCA mediante "Compute Credits" con caducidad de 90 días y zero refund (no constituyen depósito de valor); (3) Zero-Custody PSD2 via Stripe Connect split payments (dinero nunca toca cuentas de CARDEX); (4) Oráculo JWS RSA-4096 para certificados de riesgo institucional vendidos a bancos/fondos; (5) armamento normativo DMA/EU Data Act + IPFS dormant como disaster recovery ante DNS seizure.

### 10.1. ESTRUCTURA CORPORATIVA

```
CARDEX OPS AG (Zug, Suiza)
├── IP, código fuente, algoritmos
├── Cuenta de liquidación Stripe (Take-Rate)
├── Clave RSA-4096 privada del Oráculo
│
└── CARDEX EU SL (España)
    ├── Operaciones, empleados, soporte
    ├── Contrato cost-plus (5% margen sobre coste)
    └── Clientes B2B contratan directo con Suiza
```

### 10.2. SPLIT PAYMENT ATÓMICO (Anti-PSD2)

```go
params := &stripe.PaymentIntentParams{
    Amount:   stripe.Int64(vehiclePrice),    // 20.000€ → cuenta del vendedor
    Currency: stripe.String("eur"),
    TransferData: &stripe.PaymentIntentTransferDataParams{
        Destination: stripe.String(sellerAccount),
    },
    ApplicationFeeAmount: stripe.Int64(takeRate),  // 300€ → Suiza (instantáneo)
}
```

El capital fluye directamente del comprador al vendedor. CARDEX nunca custodia fondos de terceros. Sin custodia → sin obligación de licencia PSD2/EMI.

### 10.3. COMPUTE CREDITS (Anti-MiCA)

```lua
-- charge_credits.lua
local current = redis.call("INCRBY", KEYS[1], ARGV[1])
redis.call("EXPIRE", KEYS[1], 7776000)  -- 90 días TTL absoluto
return current
```

Propiedades Anti-MiCA: caducidad automática (no persistente), no reembolsable, no transferible entre usuarios, no convertible a fiat. No cumple ninguno de los 3 criterios de "instrumento de valor" bajo MiCA.

### 10.4. ORÁCULO JWS RSA-4096

Certificados de riesgo firmados para instituciones financieras:

```go
token := jwt.NewWithClaims(jwt.SigningMethodRS256, jwt.MapClaims{
    "vin":              vin,
    "collateral_clean": isClean,       // Bool: resultado de Fases 5+7
    "iss":              "CARDEX_IP_HOLDING_AG_CH",
    "exp":              time.Now().Add(24 * time.Hour).Unix(),
    "iat":              time.Now().Unix(),
})
tokenString, _ := token.SignedString(signKey)
```

El banco almacena el JWS como prueba criptográfica de la tasación de riesgo. TTL: 24h. Pricing: BPS (basis points) sobre el valor del colateral.

### 10.5. WAR ROOM LEGAL

**DMA Weaponization:** Si portales bloquean IPs del Edge fleet, denuncia ante DG COMP de la Comisión Europea por Gatekeeping bajo Digital Markets Act. Justificación legal: EU Data Act 2024 garantiza acceso a datos generados por usuarios en plataformas.

**Dormant IPFS:** Protocolo IPFS/ENS (`cardexops.eth`) compilado en el binario Tauri pero inactivo. Solo se activa si DNS seizure confisca el dominio `.com`. Los nodos Edge levantan automáticamente la red P2P para recibir actualizaciones.

---

## MAPA DE REDIS STREAMS (FLUJO END-TO-END)

```
stream:ingestion_raw  →  [Fase 4: Pipeline HFT]
                              │
                              ├─→ stream:db_write        →  [Fase 5: Tax Hunter]
                              │                                   │
                              │                                   └─→ stream:market_ready → [Fase 6: Alpha Engine]
                              │                                                                  │
                              │                                                                  └─→ stream:market_pricing → [QUIC Fan-Out]
                              │
                              ├─→ stream:visual_audit     →  [Fase 5: Cascade OCR]
                              │                                   │
                              │                                   └─→ stream:forensic_updates
                              │
                              └─→ stream:l3_pending       →  [Fase 2: L3 Qwen Worker]
                                                                  │
                                                                  └─→ dict:l1_tax (Hash)

stream:operator_events  →  [Fase 8: Karma Engine]
stream:legal_audit_pending  →  [Fase 7: Official Gov Hub]
```

---

## TOPOLOGÍA DE NODOS

| Nodo | Hardware | Función | Cores Asignados | Servicios |
|------|----------|---------|-----------------|-----------|
| 01 | AX102 | Datos (OLTP + OLAP) | CCD0: PostgreSQL, ClickHouse, Redis, PgBouncer. CCD1: Schema Watchdog, Vault | Fase 0, 1 |
| 02 | AX102 | Red + Pipeline | CCD0 (0-7): Pipeline HFT. CCD1 (16-31): Gateway QUIC/Webhooks | Fase 3, 4 |
| 03 | AX102 | IA + Forensics | CCD1 (16-23): llama-server Qwen. (24-31): Tax Hunter, OCR. (30-31): L3 Worker | Fase 2, 5 |
| 04 | AX102 | Financiero + Edge | CCD0: Alpha Engine. CCD1: QUIC Edge Gateway (HTTP/3) | Fase 6 |
| 05 | AX102 | Legal + Histórico | CCD0: ClickHouse forensics. CCD1: Official Gov Hub | Fase 7 |
| 06 | AX102 | Terminal B2B | Karma Engine, SIP Gateway, Corporate Engine | Fase 8, 10 |
| 07 | Cloudflare | CDN/SaaS | Edge SEO, CNAME flattening, TLS auto | Fase 9 |
| Fleet | Hardware clientes | Edge OSINT | Tauri/Rust, Ghost WebViews, OCR WASM local | Fase 9 |

---

## GLOSARIO DE TÉRMINOS CARDEX

| Término | Definición |
|---------|------------|
| NLC | Net Landed Cost. Coste neto total de un vehículo en destino: precio + impuestos + logística |
| SDI | Seller Desperation Index. Flag que indica que el vendedor está bajo presión financiera por curtailment cliffs |
| REBU | Régimen Especial de Bienes Usados. IVA sobre margen comercial, no deducible por el comprador |
| Banker's Buffer | Oráculo FX fail-closed que destruye activos con divisas no validadas |
| GBNF | Grammar BNF. Gramática formal que restringe outputs del LLM a nivel de decodificación |
| Karma Slashing | Sistema reputacional que penaliza especuladores con latencia artificial |
| Crypto-Shredding | Destrucción O(1) de datos cifrados mediante revocación de la DEK en Vault |
| Schema Watchdog | Microservicio que protege MaterializedPostgreSQL ante DDL mutations |
| Curtailment Cliff | Vencimiento de financiación de inventario (floorplan) a 60/90 días |
| DID | Direct Inward Dialing. Número telefónico legal alquilado para routing SIP |
| Compute Credits | Unidades de acceso con TTL 90d, no reembolsables (Anti-MiCA) |
| Quote ID | HMAC-SHA256 del estado del vehículo en el instante de la cotización |

---

---

# BLOQUE B: DATA MODELS

## B.1. PostgreSQL OLTP — DDL Canónico

Régimen: V2 Bloque 6 define el modelo conceptual (Vehicle, Listing, Dealer, Mandate, Score, RiskFlag, User). V6 redefine la implementación con UUIDv7, FILLFACTOR, HOT updates y particionamiento por tenant. La síntesis produce el siguiente DDL ejecutable.

### B.1.1. Extensiones y Configuración Base

```sql
-- Nodo 01: PostgreSQL 16 sobre ZFS (recordsize=8k)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";     -- Búsqueda fuzzy por nombre
CREATE EXTENSION IF NOT EXISTS "btree_gist";  -- Exclusion constraints temporales

-- UUIDv7 monotónico (compatible con B-tree ordering, elimina UUID random scatter)
CREATE OR REPLACE FUNCTION uuidv7() RETURNS uuid AS $$
DECLARE
  ts bigint := (extract(epoch from clock_timestamp()) * 1000)::bigint;
  bytes bytea := decode(lpad(to_hex(ts), 12, '0'), 'hex') || gen_random_bytes(10);
BEGIN
  -- Set version (7) and variant (2) bits
  bytes := set_byte(bytes, 6, (get_byte(bytes, 6) & x'0f'::int) | x'70'::int);
  bytes := set_byte(bytes, 8, (get_byte(bytes, 8) & x'3f'::int) | x'80'::int);
  RETURN encode(bytes, 'hex')::uuid;
END;
$$ LANGUAGE plpgsql VOLATILE;
```

### B.1.2. Tablas Maestras

```sql
-- ═══════════════════════════════════════════════════════
-- TENANT (Multi-tenancy por país/organización)
-- ═══════════════════════════════════════════════════════
CREATE TABLE tenant (
  tenant_id    smallint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  code         varchar(4) NOT NULL UNIQUE,      -- "ES", "DE", "FR", "NL"
  name         text NOT NULL,
  currency     char(3) NOT NULL DEFAULT 'EUR',
  timezone     text NOT NULL DEFAULT 'Europe/Madrid',
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- ═══════════════════════════════════════════════════════
-- DEALER (Concesionario / Vendedor B2B)
-- ═══════════════════════════════════════════════════════
CREATE TABLE dealer (
  dealer_id    uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id    smallint NOT NULL REFERENCES tenant(tenant_id),
  name         text NOT NULL,
  vat_id       varchar(20),                     -- NIF/VAT europeo
  country      char(2) NOT NULL,
  city         text,
  tier         varchar(20) NOT NULL DEFAULT 'FREE'
                 CHECK (tier IN ('FREE','PRO','CROSS_BORDER','ENTERPRISE')),
  karma        smallint NOT NULL DEFAULT 100 CHECK (karma BETWEEN 0 AND 200),
  stripe_account_id varchar(64),                -- Stripe Connect account
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
) WITH (fillfactor = 70);

CREATE INDEX idx_dealer_tenant ON dealer(tenant_id);
CREATE INDEX idx_dealer_vat ON dealer(vat_id) WHERE vat_id IS NOT NULL;
CREATE INDEX idx_dealer_name_trgm ON dealer USING gist (name gist_trgm_ops);

-- ═══════════════════════════════════════════════════════
-- VEHICLE (Entidad inmutable del vehículo físico)
-- ═══════════════════════════════════════════════════════
CREATE TABLE vehicle (
  vehicle_id   uuid PRIMARY KEY DEFAULT uuidv7(),
  vin          char(17) NOT NULL,
  fingerprint  char(64) NOT NULL UNIQUE,         -- SHA-256(VIN+color+mileage)
  make         text NOT NULL,
  model        text NOT NULL,
  year         smallint NOT NULL CHECK (year BETWEEN 1900 AND 2030),
  fuel_type    varchar(20) CHECK (fuel_type IN ('PETROL','DIESEL','ELECTRIC','HYBRID','LPG','CNG')),
  co2_grams    smallint CHECK (co2_grams >= 0),
  color        text,
  transmission varchar(10) CHECK (transmission IN ('MANUAL','AUTO')),
  body_type    varchar(20),
  h3_index     varchar(16),                      -- Uber H3 resolution 4
  source       text NOT NULL,                    -- "B2B_WEBHOOK", "EDGE_FLEET"
  source_id    text,                             -- ID original del portal
  raw_description text,                          -- Texto completo del anuncio
  thumb_url    text,
  ingested_at  timestamptz NOT NULL DEFAULT now(),
  -- Campos cifrados (Vault envelope encryption, AES-256-GCM)
  dek_id       uuid,                             -- Referencia a Vault DEK
  encrypted_seller_name bytea,
  encrypted_seller_phone bytea,
  encrypted_seller_email bytea
);

CREATE INDEX idx_vehicle_vin ON vehicle(vin);
CREATE INDEX idx_vehicle_h3 ON vehicle(h3_index) WHERE h3_index IS NOT NULL;
CREATE INDEX idx_vehicle_make_model ON vehicle(make, model);
CREATE INDEX idx_vehicle_ingested ON vehicle(ingested_at DESC);

-- ═══════════════════════════════════════════════════════
-- LISTING (Anuncio activo — estado mutable del vehículo en mercado)
-- ═══════════════════════════════════════════════════════
CREATE TABLE listing (
  listing_id       uuid PRIMARY KEY DEFAULT uuidv7(),
  vehicle_id       uuid NOT NULL REFERENCES vehicle(vehicle_id),
  seller_dealer_id uuid REFERENCES dealer(dealer_id),
  tenant_id        smallint NOT NULL REFERENCES tenant(tenant_id),
  seller_type      varchar(10) NOT NULL CHECK (seller_type IN ('DEALER','PRIVATE','FLEET','AUCTION')),

  -- Pricing chain
  price_raw        numeric(12,2) NOT NULL CHECK (price_raw > 0),
  currency_raw     char(3) NOT NULL,
  gross_physical_cost numeric(12,2),             -- After FX + damage repair (Fase 4)
  net_landed_cost  numeric(12,2),                -- After taxes + logistics (Fase 6)
  quote_id         char(64),                     -- HMAC-SHA256 quote

  -- Fiscalidad
  tax_status       varchar(30) NOT NULL DEFAULT 'PENDING'
                     CHECK (tax_status IN ('DEDUCTIBLE','REBU','REQUIRES_HUMAN_AUDIT',
                                           'PENDING','PENDING_VIES_OPTIMISTIC','UNKNOWN')),
  tax_confidence   real CHECK (tax_confidence BETWEEN 0.0 AND 1.0),
  vies_status      varchar(20) DEFAULT 'NOT_CHECKED',

  -- Estado comercial
  status           varchar(20) NOT NULL DEFAULT 'ACTIVE'
                     CHECK (status IN ('ACTIVE','RESERVED','SOLD','EXPIRED','FRAUD_BLOCKED')),
  days_on_market   smallint NOT NULL DEFAULT 0 CHECK (days_on_market >= 0),
  sdi_alert        boolean NOT NULL DEFAULT false,

  -- Legal
  legal_status     varchar(30) DEFAULT 'NOT_CHECKED'
                     CHECK (legal_status IN ('NOT_CHECKED','LEGAL_CLEAR','LEGAL_LIEN_OR_STOLEN',
                                             'LEGAL_TIMEOUT','LEGAL_UNKNOWN',
                                             'FRAUD_ODOMETER_ROLLBACK')),
  mileage          integer NOT NULL CHECK (mileage >= 0),
  mileage_verified boolean NOT NULL DEFAULT false,

  -- Timestamps
  published_at     timestamptz NOT NULL DEFAULT now(),
  reserved_at      timestamptz,
  sold_at          timestamptz,
  updated_at       timestamptz NOT NULL DEFAULT now()
) WITH (fillfactor = 70);

CREATE INDEX idx_listing_vehicle ON listing(vehicle_id);
CREATE INDEX idx_listing_tenant_status ON listing(tenant_id, status) WHERE status = 'ACTIVE';
CREATE INDEX idx_listing_nlc ON listing(net_landed_cost) WHERE status = 'ACTIVE';
CREATE INDEX idx_listing_sdi ON listing(sdi_alert, days_on_market) WHERE sdi_alert = true;

-- ═══════════════════════════════════════════════════════
-- MANDATE (Mandato Vivo — orden de búsqueda persistente)
-- ═══════════════════════════════════════════════════════
CREATE TABLE mandate (
  mandate_id   uuid PRIMARY KEY DEFAULT uuidv7(),
  dealer_id    uuid NOT NULL REFERENCES dealer(dealer_id),
  tenant_id    smallint NOT NULL REFERENCES tenant(tenant_id),
  name         text NOT NULL,                    -- "BMW Serie 3 < 15k NLC"
  status       varchar(15) NOT NULL DEFAULT 'ACTIVE'
                 CHECK (status IN ('ACTIVE','PAUSED','FULFILLED','EXPIRED')),

  -- Criterios de búsqueda (JSONB para flexibilidad máxima)
  criteria     jsonb NOT NULL,
  -- Ejemplo: {"makes":["BMW","Audi"], "models":["Serie 3","A4"],
  --           "year_min":2018, "year_max":2022, "nlc_max":15000,
  --           "fuel":["DIESEL","HYBRID"], "markets":["DE","FR","NL"],
  --           "risk_max":"MEDIUM", "min_margin_pct": 12}

  -- Ejecución
  vehicles_target   smallint DEFAULT 1,
  vehicles_acquired smallint NOT NULL DEFAULT 0,
  progress_pct      real GENERATED ALWAYS AS (
    CASE WHEN vehicles_target > 0
         THEN LEAST(100.0, (vehicles_acquired::real / vehicles_target) * 100)
         ELSE 0 END
  ) STORED,

  -- Alertas
  alert_channels jsonb DEFAULT '["push","email"]',
  alert_threshold real DEFAULT 0.90,             -- Score mínimo para notificación

  created_at   timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz,
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_mandate_dealer ON mandate(dealer_id);
CREATE INDEX idx_mandate_active ON mandate(status) WHERE status = 'ACTIVE';

-- ═══════════════════════════════════════════════════════
-- TRADE_TICKET (Orden de operación ejecutada)
-- ═══════════════════════════════════════════════════════
CREATE TABLE trade_ticket (
  ticket_id    uuid PRIMARY KEY DEFAULT uuidv7(),
  listing_id   uuid NOT NULL REFERENCES listing(listing_id),
  mandate_id   uuid REFERENCES mandate(mandate_id),
  buyer_id     uuid NOT NULL REFERENCES dealer(dealer_id),
  seller_id    uuid REFERENCES dealer(dealer_id),

  -- Financials
  execution_price  numeric(12,2) NOT NULL,
  take_rate        numeric(10,2) NOT NULL,       -- Comisión CARDEX
  stripe_pi_id     varchar(64),                  -- Stripe PaymentIntent ID

  -- Legal escrow
  legal_status_at_execution varchar(30) NOT NULL,
  waiver_signed    boolean NOT NULL DEFAULT false,

  -- Quote verification
  quote_id_verified char(64) NOT NULL,
  quote_match      boolean NOT NULL DEFAULT true,

  status           varchar(15) NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING','CONFIRMED','CANCELLED','DISPUTED')),

  executed_at  timestamptz NOT NULL DEFAULT now(),
  confirmed_at timestamptz
);

CREATE INDEX idx_ticket_buyer ON trade_ticket(buyer_id);
CREATE INDEX idx_ticket_listing ON trade_ticket(listing_id);

-- ═══════════════════════════════════════════════════════
-- CREDITS (Compute Credits Anti-MiCA, TTL 90d)
-- ═══════════════════════════════════════════════════════
CREATE TABLE credit_ledger (
  entry_id     uuid PRIMARY KEY DEFAULT uuidv7(),
  dealer_id    uuid NOT NULL REFERENCES dealer(dealer_id),
  amount       integer NOT NULL,                 -- Positivo = compra, negativo = consumo
  balance_after integer NOT NULL,
  reason       varchar(30) NOT NULL
                 CHECK (reason IN ('PURCHASE','CONSUMPTION','EXPIRY','WELCOME_BONUS')),
  expires_at   timestamptz NOT NULL DEFAULT (now() + interval '90 days'),
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_credits_dealer ON credit_ledger(dealer_id, created_at DESC);
CREATE INDEX idx_credits_expiry ON credit_ledger(expires_at) WHERE amount > 0;

-- ═══════════════════════════════════════════════════════
-- RISK_FLAG (Flags de fraude y anomalía)
-- ═══════════════════════════════════════════════════════
CREATE TABLE risk_flag (
  flag_id      uuid PRIMARY KEY DEFAULT uuidv7(),
  entity_type  varchar(10) NOT NULL CHECK (entity_type IN ('VEHICLE','LISTING','DEALER')),
  entity_id    uuid NOT NULL,
  flag_type    varchar(30) NOT NULL
                 CHECK (flag_type IN ('ODOMETER_ROLLBACK','TITLE_WASHING','PRICE_ANOMALY',
                                      'STOLEN_VIN','DUPLICATE_FRAUD','AHO_CORASICK_MARGIN',
                                      'VIES_INVALID','SELLER_BLACKLISTED')),
  severity     varchar(10) NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  detail       jsonb,
  resolved     boolean NOT NULL DEFAULT false,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_riskflag_entity ON risk_flag(entity_type, entity_id);
CREATE INDEX idx_riskflag_unresolved ON risk_flag(severity) WHERE resolved = false;

-- ═══════════════════════════════════════════════════════
-- AUDIT_LOG (Lineage y trazabilidad completa)
-- ═══════════════════════════════════════════════════════
CREATE TABLE audit_log (
  log_id       bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  entity_type  varchar(20) NOT NULL,
  entity_id    uuid NOT NULL,
  action       varchar(20) NOT NULL,             -- INSERT, UPDATE, DELETE, VALIDATE, ENRICH
  actor        varchar(40) NOT NULL,             -- "pipeline_v2", "tax_hunter", "user:<id>"
  old_value    jsonb,
  new_value    jsonb,
  metadata     jsonb,                            -- {source, parser_version, confidence, ...}
  created_at   timestamptz NOT NULL DEFAULT now()
) PARTITION BY RANGE (created_at);

-- Particiones mensuales (auto-crear via pg_partman o cron)
CREATE TABLE audit_log_2026_01 PARTITION OF audit_log
  FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE audit_log_2026_02 PARTITION OF audit_log
  FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
-- ... (script de auto-creación mensual)
```

### B.1.3. Row-Level Security (Multi-Tenancy)

```sql
ALTER TABLE listing ENABLE ROW LEVEL SECURITY;
ALTER TABLE mandate ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_listing ON listing
  USING (tenant_id = current_setting('app.current_tenant')::smallint);

CREATE POLICY tenant_isolation_mandate ON mandate
  USING (tenant_id = current_setting('app.current_tenant')::smallint);

-- Roles
CREATE ROLE etl_writer;
GRANT INSERT, UPDATE ON vehicle, listing TO etl_writer;

CREATE ROLE analyst_read;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst_read;

CREATE ROLE dealer_api;
GRANT SELECT ON listing, vehicle, mandate TO dealer_api;
GRANT INSERT, UPDATE ON mandate, trade_ticket TO dealer_api;
```

### B.1.4. Publication para Zero-PII ClickHouse

```sql
-- Vista filtrada que excluye PII (campos encrypted_*)
CREATE VIEW listing_olap_safe AS
SELECT
  l.listing_id, l.vehicle_id, l.tenant_id, l.seller_type,
  l.price_raw, l.currency_raw, l.gross_physical_cost, l.net_landed_cost,
  l.tax_status, l.tax_confidence, l.status, l.days_on_market, l.sdi_alert,
  l.mileage, l.published_at, l.updated_at,
  v.vin, v.fingerprint, v.make, v.model, v.year, v.fuel_type,
  v.co2_grams, v.h3_index, v.source
FROM listing l
JOIN vehicle v ON v.vehicle_id = l.vehicle_id;

-- Publication sobre la vista (ClickHouse MaterializedPostgreSQL consume esto)
CREATE PUBLICATION cardex_olap_pub FOR TABLE listing, vehicle;
-- Nota: MaterializedPostgreSQL no soporta views directamente.
-- El Schema Watchdog filtra columnas encrypted_* post-replicación.
```

## B.2. ClickHouse OLAP — DDL Canónico

```sql
-- ═══════════════════════════════════════════════════════
-- INVENTARIO DE MERCADO (Réplica OLAP, Zero-PII)
-- ═══════════════════════════════════════════════════════
CREATE DATABASE IF NOT EXISTS cardex_market;

CREATE TABLE cardex_market.vehicle_inventory (
  listing_id     UUID,
  vehicle_id     UUID,
  tenant_id      UInt16,
  vin            FixedString(17),
  fingerprint    FixedString(64),
  make           String,
  model          String,
  year           UInt16,
  fuel_type      LowCardinality(String),
  co2_grams      UInt16,
  h3_index       String,
  source         LowCardinality(String),
  seller_type    LowCardinality(String),
  price_raw      Decimal64(2),
  gross_physical_cost Decimal64(2),
  net_landed_cost     Decimal64(2),
  tax_status     LowCardinality(String),
  tax_confidence Float32,
  status         LowCardinality(String),
  days_on_market UInt16,
  sdi_alert      UInt8,
  mileage        UInt32,
  published_at   DateTime,
  updated_at     DateTime
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (tenant_id, make, model, listing_id)
PARTITION BY toYYYYMM(published_at)
SETTINGS index_granularity = 8192;

-- ═══════════════════════════════════════════════════════
-- FORENSICS
-- ═══════════════════════════════════════════════════════
CREATE DATABASE IF NOT EXISTS cardex_forensics;

CREATE TABLE cardex_forensics.salvage_ledger (
  vin           String,
  phash         UInt64,                          -- Perceptual hash para image matching
  source        LowCardinality(String),
  damage_zone   String,
  auction_date  Date,
  INDEX idx_vin vin TYPE bloom_filter GRANULARITY 1
) ENGINE = MergeTree()
ORDER BY (auction_date, vin)
SETTINGS index_granularity = 8192;

CREATE TABLE cardex_forensics.mileage_history (
  vin           String,
  recorded_date Date,
  mileage       UInt32,
  country       LowCardinality(FixedString(2))
) ENGINE = MergeTree()
ORDER BY (vin, recorded_date);

-- ═══════════════════════════════════════════════════════
-- STAR SCHEMA: TABLA DE HECHOS (Eventos de vehículo)
-- ═══════════════════════════════════════════════════════
CREATE DATABASE IF NOT EXISTS cardex_analytics;

CREATE TABLE cardex_analytics.fact_vehicle_events (
  event_id      UUID DEFAULT generateUUIDv4(),
  event_type    LowCardinality(String),          -- INGESTED, PRICED, RESERVED, SOLD, EXPIRED, FLAGGED
  listing_id    UUID,
  vehicle_id    UUID,

  -- Dimension keys
  tenant_id     UInt16,
  make          LowCardinality(String),
  model         String,
  seller_type   LowCardinality(String),
  h3_index      String,
  fuel_type     LowCardinality(String),

  -- Measures
  price_raw     Decimal64(2),
  net_landed_cost Decimal64(2),
  margin_pct    Float32,
  days_on_market UInt16,
  tax_confidence Float32,
  risk_severity LowCardinality(String),          -- NONE, LOW, MEDIUM, HIGH, CRITICAL

  -- Time
  event_date    Date,
  event_ts      DateTime
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (event_date, tenant_id, make, event_type)
SETTINGS index_granularity = 8192;

-- ═══════════════════════════════════════════════════════
-- MATERIALIZED VIEWS (Cubos pre-agregados)
-- ═══════════════════════════════════════════════════════

-- Cubo: Pricing por marca/país/mes
CREATE MATERIALIZED VIEW cardex_analytics.mv_pricing_cube
ENGINE = AggregatingMergeTree()
ORDER BY (event_month, tenant_id, make)
AS SELECT
  toStartOfMonth(event_date) AS event_month,
  tenant_id, make,
  avgState(net_landed_cost)  AS avg_nlc,
  minState(net_landed_cost)  AS min_nlc,
  maxState(net_landed_cost)  AS max_nlc,
  countState()               AS vehicle_count
FROM cardex_analytics.fact_vehicle_events
WHERE event_type = 'PRICED'
GROUP BY event_month, tenant_id, make;

-- Cubo: Liquidez (velocidad de venta)
CREATE MATERIALIZED VIEW cardex_analytics.mv_liquidity_cube
ENGINE = AggregatingMergeTree()
ORDER BY (event_month, tenant_id, make, seller_type)
AS SELECT
  toStartOfMonth(event_date) AS event_month,
  tenant_id, make, seller_type,
  avgState(days_on_market)   AS avg_days_to_sell,
  countState()               AS sold_count
FROM cardex_analytics.fact_vehicle_events
WHERE event_type = 'SOLD'
GROUP BY event_month, tenant_id, make, seller_type;

-- Cubo: Risk monitoring
CREATE MATERIALIZED VIEW cardex_analytics.mv_risk_cube
ENGINE = AggregatingMergeTree()
ORDER BY (event_month, tenant_id, risk_severity)
AS SELECT
  toStartOfMonth(event_date) AS event_month,
  tenant_id, risk_severity,
  countState() AS flag_count
FROM cardex_analytics.fact_vehicle_events
WHERE event_type = 'FLAGGED'
GROUP BY event_month, tenant_id, risk_severity;
```

## B.3. Redis Key Schema

```
# ──────────── Core State ────────────
vehicle_state:<hash>          HASH  {vin, mileage, quote_id, legal_status, nlc, ...}
lock:<hash>                   STRING (buyer_id, TTL 120s)  -- Mutex atómico
bloom:vehicles                BF    (50M capacity, 0.01% FPR)
dict:l1_tax                   HASH  {<vehicle_id>: {tax_status, confidence}}
fx_buffer                     HASH  {EUR:1.0, PLN:0.234, CZK:0.041, ...}

# ──────────── Streams ────────────
stream:ingestion_raw          →  Pipeline HFT (Fase 4)
stream:db_write               →  Tax Hunter (Fase 5)
stream:visual_audit           →  Cascade OCR (Fase 5)
stream:l3_pending             →  L3 Qwen Worker (Fase 2)
stream:market_ready           →  Alpha Engine (Fase 6)
stream:market_pricing         →  QUIC Fan-Out
stream:legal_audit_pending    →  Official Gov Hub (Fase 7)
stream:operator_events        →  Karma Engine (Fase 8)
stream:forensic_updates       →  DB Write (VIN extraction)

# ──────────── Karma & Throttling ────────────
karma:<buyer_id>              STRING (integer 0-200, default 100)
throttling_tier               HASH  {<buyer_id>: latency_ms}

# ──────────── Rate Limiting ────────────
ratelimit:<source_id>         STRING (tokens remaining)
ratelimit:<source_id>:ts      STRING (last refill timestamp)

# ──────────── Logistics & Tax Oracles ────────────
logistics:worst_case          HASH  {DE:1050.00, FR:750.00, NL:950.00, ...}
b2b_rosetta:<SOURCE>          HASH  {<damage_code>: repair_cost}

# ──────────── MiCA Credits ────────────
credits:<dealer_id>           STRING (integer, TTL 7776000 = 90d)

# ──────────── Pub/Sub ────────────
channel:live_market           PUBSUB  (SSE fan-out to QUIC clients)
```

---

# BLOQUE C: PRODUCT DESIGN & LIFECYCLE

## C.1. Mandato Vivo (Unidad Atómica)

El Mandato Vivo es la unidad de negocio central de CARDEX. No es una búsqueda — es una orden de compra algorítmica persistente que activa todo el motor.

### C.1.1. Lifecycle del Mandato

```
CREATED ──→ ACTIVE ──→ FULFILLED
                │            │
                ├─→ PAUSED   │
                │     │      │
                │     └──→ ACTIVE
                │
                └─→ EXPIRED (auto, si expires_at alcanzado)
```

**Estados:**

| Estado | Trigger | Comportamiento del sistema |
|--------|---------|---------------------------|
| ACTIVE | Dealer crea/reactiva mandato | Motor de matching corre contra cada vehículo que entra al pipeline. Si listing.score ≥ mandate.alert_threshold → push notification |
| PAUSED | Dealer pausa manualmente | Matching suspendido. Sin alertas. El mandato sigue visible en dashboard |
| FULFILLED | vehicles_acquired == vehicles_target | Matching desactivado. Informe de cierre generado automáticamente |
| EXPIRED | now() > expires_at | Equivalente a FULFILLED pero sin completar. Informe parcial disponible |

### C.1.2. Matching Engine

Cada vehículo que completa la Fase 6 (NLC calculado) se evalúa contra todos los mandatos ACTIVE:

```
Para cada mandato ACTIVE:
  1. Filter: make ∈ criteria.makes AND model ∈ criteria.models
  2. Filter: year BETWEEN criteria.year_min AND criteria.year_max
  3. Filter: nlc ≤ criteria.nlc_max
  4. Filter: fuel_type ∈ criteria.fuel
  5. Filter: h3_index ∈ criteria.markets (convertido a H3)
  6. Score: CARDEX_SCORE = f(margin_pct, liquidity_days, risk_severity, sdi_alert)
  7. Si CARDEX_SCORE ≥ mandate.alert_threshold → NOTIFY
```

El CARDEX Score es un compuesto ponderado:

```
CARDEX_SCORE = 0.35 × margin_score
             + 0.25 × liquidity_score
             + 0.25 × (1 - risk_score)
             + 0.15 × sdi_bonus
```

Donde `margin_score` = percentil del margen sobre mercado comparable, `liquidity_score` = inverso de días esperados en mercado, `risk_score` = severidad normalizada de risk_flags, `sdi_bonus` = 0.15 si sdi_alert == true (oportunidad de low-balling).

## C.2. Lifecycle del Vehículo

```
INGESTED (Fase 3)
    │
    ├─→ DEDUPLICATED (Fase 4, Bloom) → DROP si duplicado
    │
    ├─→ PRICED (Fase 4, GrossPhysicalCost calculado)
    │
    ├─→ CLASSIFIED (Fase 5, TaxStatus asignado)
    │     ├─→ Si REQUIRES_HUMAN_AUDIT → cola de revisión manual
    │     └─→ Si DEDUCTIBLE/REBU → continúa
    │
    ├─→ NLC_CALCULATED (Fase 6, NetLandedCost + Quote firmado)
    │
    ├─→ ACTIVE (publicado en Dark Pool, visible para dealers)
    │     │
    │     ├─→ RESERVED (Mutex lock 120s, Escrow iniciado)
    │     │     │
    │     │     ├─→ LEGAL_CHECK (Fase 7, API B2B oficial)
    │     │     │     ├─→ LEGAL_CLEAR → SOLD
    │     │     │     ├─→ LEGAL_LIEN_OR_STOLEN → FRAUD_BLOCKED
    │     │     │     └─→ LEGAL_TIMEOUT → SOLD (con Waiver) o ACTIVE (reserva expirada)
    │     │     │
    │     │     └─→ RESERVE_EXPIRED → ACTIVE (karma -15 al buyer)
    │     │
    │     └─→ EXPIRED (days_on_market > threshold)
    │
    └─→ FRAUD_BLOCKED (cualquier fase, si RiskFlag severity=CRITICAL)
```

## C.3. Terminal Dark Pool — Flujo UI

**Panel principal (Virtual Scroller, 30 nodos reciclados):**

La interfaz es un feed vertical ordenado por NLC ascendente (los mejores deals primero). Cada tarjeta muestra: foto miniatura, make/model/year, NLC con desglose on-hover (gross + taxes + logistics), tax_status badge (verde=DEDUCTIBLE, naranja=REBU, rojo=AUDIT), days_on_market counter, SDI pulse animation si sdi_alert=true, y CARDEX_SCORE como barra radial.

**Acciones por vehículo:**

| Botón | Acción backend | Resultado UI |
|-------|----------------|-------------|
| "Reservar" | Lua Mutex + HMAC verify | Lock 120s. Timer visible. Escrow Fase 7 iniciado |
| "Detallar" | Consume 1 crédito | Expande ficha: historial, fotos HD, informe completo |
| "Llamar" | SIP Gateway → Twilio DID | WebRTC call desde navegador. DID local del país del vendedor |
| "Añadir a Mandato" | UPDATE mandate SET vehicles_acquired++ | Trade Ticket generado |

**Dashboard de Mandato Vivo:**

Barra de progreso (vehicles_acquired / vehicles_target), historial de oportunidades presentadas (aceptadas/rechazadas con motivo), gráfico temporal de NLC promedio en el segmento del mandato, mapa H3 de concentración de oferta.

---

# BLOQUE D: UNIT ECONOMICS & PRICING

## D.1. Estructura de Pricing (V2 Bloque 8 + V6 Anti-MiCA)

### D.1.1. Planes de Suscripción

| Plan | Precio/mes | Créditos incluidos | Fuentes | Mandatos activos | Usuarios | API |
|------|------------|-------------------|---------|-----------------|----------|-----|
| FREE | 0€ | 50 (welcome, one-time) | 2 mercados | 1 | 1 | No |
| PRO | 299€ | 500/mes | Nacional (1 país completo) | 5 | 3 | Básica |
| CROSS-BORDER | 599€ | 1.500/mes | Pan-EU (todos los mercados) | 15 | 5 | Completa |
| ENTERPRISE | 1.499€ | Ilimitados | Pan-EU + custom feeds | Ilimitados | SSO ilimitado | Dedicada + Webhooks |

Todos los créditos tienen TTL de 90 días (Anti-MiCA). No son reembolsables ni transferibles.

### D.1.2. Consumo de Créditos

| Acción | Créditos | Justificación de coste |
|--------|----------|----------------------|
| Ver detalle de listing | 1 | Lectura enriquecida + imágenes HD |
| Informe historial VIN (básico) | 5 | Consulta interna ClickHouse |
| Informe historial VIN (completo) | 15 | Consulta externa IDEAUTO/CARFAX (1-3€ OPEX) |
| Generación informe IA (mercado) | 10 | L3 Qwen inference (~0.10€ compute) |
| Reserva de vehículo | 0 | Incluido en suscripción (incentiva transacción) |
| Alerta push por mandato | 0 | Incluido en suscripción |

### D.1.3. Comisiones Transaccionales

| Tipo | Comisión | Mecanismo |
|------|----------|-----------|
| Compra via Dark Pool | 1.5% del precio (min 150€, max 500€) | Split Payment Stripe Connect |
| Take-rate a Holding Suiza | Incluido en comisión | ApplicationFeeAmount automático |
| Oráculo JWS para bancos | 25-50 BPS del valor del colateral | Facturación B2B directa |

## D.2. Estructura de Costes

### D.2.1. OPEX Mensual (Infraestructura)

| Concepto | Coste/mes | Notas |
|----------|-----------|-------|
| 3× Hetzner AX102 (base) | 327€ | AMD 7950X3D, 128GB, 2×NVMe |
| 3× Hetzner AX102 (expansión) | 327€ | Nodos 04-06 |
| Ancho de banda (30TB) | ~90€ | Hetzner traffic pool |
| Twilio SIP (DIDs + minutos) | ~200€ | 5 DIDs EU + ~2.000 min/mes |
| Stripe fees (2.9% + 0.30€) | Variable | Sobre volumen transaccional |
| APIs B2B legales (IDEAUTO, CARFAX) | ~500€ | ~200 consultas/mes × 2.50€ |
| Cloudflare for SaaS | ~50€ | 100 custom domains |
| EV Code Signing cert | ~33€ | 400€/año amortizado |
| Dominios + DNS | ~15€ | Cluster + TLDs |
| **Total fijo** | **~1.542€** | Sin Stripe variable |

### D.2.2. OPEX Variable (por Vehículo Procesado)

| Fase | Coste unitario | Volumen estimado | Total/mes |
|------|----------------|------------------|-----------|
| Ingesta + Dedup (Fase 3-4) | ~0.001€ | 500K vehículos | 500€ |
| Tax Classification (Fase 5) | ~0.01€ (L3: ~0.05€) | 100K nuevos | 1.000€ |
| NLC Calculation (Fase 6) | ~0.001€ | 100K | 100€ |
| Legal Check (Fase 7) | ~2.50€ | 200 reservas | 500€ |
| **Total variable** | | | **~2.100€** |

### D.2.3. OPEX Total Proyectado

| Mes | Dealers activos | OPEX total | Revenue | Margen |
|-----|-----------------|------------|---------|--------|
| M1 (lanzamiento) | 20 | 3.642€ | 2.000€ | -45% |
| M6 | 80 | 5.200€ | 12.000€ | +131% |
| M12 | 200 | 8.500€ | 45.000€ | +429% |
| M18 | 500 | 14.000€ | 120.000€ | +757% |
| M24 | 1.000 | 22.000€ | 280.000€ | +1.172% |
| M36 | 2.500 | 45.000€ | 750.000€ | +1.567% |

## D.3. Break-Even Analysis

```
Break-even mensual = OPEX_fijo / (ARPU - OPEX_variable_por_dealer)

Con ARPU estimado (mix de planes):
  - 40% FREE (0€)
  - 35% PRO (299€)
  - 15% CROSS-BORDER (599€)
  - 10% ENTERPRISE (1.499€)
  
  ARPU ponderado = 0 + 104.65 + 89.85 + 149.90 = 344.40€

OPEX_variable_por_dealer ≈ 25€ (consultas, compute, APIs proporcional)

Break-even = 1.542€ / (344.40€ - 25€) = ~5 dealers de pago

Con conversion rate freemium → pago del 25%:
  Break-even en dealers totales = 5 / 0.25 = ~20 dealers registrados
```

**Conclusión:** El modelo es viable con ~20 dealers registrados (5 de pago). El apalancamiento operativo es extremo: los costes fijos se diluyen rápidamente y el OPEX variable es marginal por dealer.

## D.4. Revenue Projections (36 Meses)

| Fuente de ingreso | M6 | M12 | M24 | M36 |
|-------------------|-----|------|------|------|
| Suscripciones | 8.000€ | 30.000€ | 180.000€ | 500.000€ |
| Créditos extra | 1.500€ | 5.000€ | 30.000€ | 80.000€ |
| Comisiones transaccionales | 2.000€ | 8.000€ | 60.000€ | 140.000€ |
| Oráculo JWS (bancos) | 0€ | 0€ | 5.000€ | 20.000€ |
| Servicios auxiliares (logística) | 500€ | 2.000€ | 5.000€ | 10.000€ |
| **Total** | **12.000€** | **45.000€** | **280.000€** | **750.000€** |

**Métricas SaaS clave (M24):**

| Métrica | Valor | Benchmark SaaS |
|---------|-------|---------------|
| ARPU (paying) | ~560€/mes | Saludable para B2B vertical |
| LTV/CAC (SMB) | >8x | >3x = saludable |
| Gross Margin | >80% | Típico SaaS |
| Net Revenue Retention | >115% | Expansión por upsell Cross-Border→Enterprise |
| Churn mensual | <3% | <5% = saludable para SMB |

---

# BLOQUE E: AUDIT FORENSE FORMAL

## E.1. Tabla de Elementos Ilegales Purgados (V4 → V6)

| # | Elemento V4 | Artículo/Ley violado | Acción V6 | Estado |
|---|-------------|---------------------|-----------|--------|
| E-01 | SSL Unpinning (Frida) | Art. 197 CP (ES), CFAA (US) | Eliminado. Sustituido por Webhooks B2B licenciados | ✅ PURGADO |
| E-02 | API Ghosting (DGT/RDW) | Acceso no autorizado a sistemas informáticos | Sustituido por APIs B2B de pago (IDEAUTO) | ✅ PURGADO |
| E-03 | DID Spoofing (Caller ID falso) | EU Telecom Act, Ley 11/2022 (ES) | Sustituido por Twilio DIDs legales con STIR/SHAKEN | ✅ PURGADO |
| E-04 | Dark Web scraping (subastas de siniestros) | Receptación digital, violación de ToS | Sustituido por suscripción B2B CARFAX/AutoDNA | ✅ PURGADO |
| E-05 | ReDroid/Android emulation | Evasión de mecanismos de protección | Eliminado. Edge fleet usa EU Data Act | ✅ PURGADO |
| E-06 | SS7/HLR Lookup no autorizado | Interceptación de telecomunicaciones | Eliminado completamente. Sin sustituto | ✅ PURGADO |
| E-07 | Financial slashing (deducción de saldo real) | Cobro no autorizado, chargebacks | Sustituido por Karma Slashing reputacional | ✅ PURGADO |
| E-08 | Idle Slashing (penalización por inactividad) | Cláusula abusiva (Dir. 93/13/CEE) | Eliminado. Credits expiran por TTL, no por penalización | ✅ PURGADO |
| E-09 | "ZKP" falso (booleano simple) | Publicidad engañosa | Sustituido por JWS RSA-4096 auditable | ✅ PURGADO |
| E-10 | Proxy rotation masivo (residential IPs) | Evasión de medidas técnicas | Eliminado. Ingesta via webhooks o Edge fleet legal | ✅ PURGADO |

## E.2. Riesgos Legales Residuales

| # | Riesgo | Severidad | Mitigación implementada | Riesgo residual |
|---|--------|-----------|------------------------|----------------|
| R-01 | EU Data Act: interpretación de "datos generados por el usuario" podría no cubrir scraping delegado | MEDIA | El concesionario cliente ejecuta la extracción con su propia IP y bajo su consentimiento | Litigio posible si un portal impugna. Mitigación: DMA como segundo escudo legal |
| R-02 | RGPD: datos de vendedores privados (nombre, teléfono) | ALTA | Envelope encryption Vault + crypto-shredding O(1) + Zero-PII en ClickHouse | Requiere DPO designado y DPIA completado antes de producción |
| R-03 | Anti-MiCA: regulador podría reclasificar Compute Credits | BAJA | TTL 90d, no reembolsable, no transferible, no convertible. Documentación legal previa | Monitorizar guidance de ESMA |
| R-04 | Anti-PSD2: Stripe Connect split payment podría reclasificarse como custodia | BAJA | CARDEX nunca toca fondos. Stripe es el PSP regulado. Documentación del flujo | Consultar con abogado fintech pre-lanzamiento |
| R-05 | Estructura Suiza: Transfer Pricing scrutiny | MEDIA | Cost-plus 5% documentado. Sustancia real en Suiza (IP, servidores, decisiones) | Requiere Transfer Pricing study formal |
| R-06 | SEO JSON-LD: Google podría penalizar la estructura semántica como manipulación | BAJA | Schema.org estándar. No link farm. Sin cloaking | Monitorizar Search Console |
| R-07 | Ghost WebViews: actualización de OS podría bloquear ventanas invisibles | MEDIA | Fallback a extracción manual via UI visible + Passive QoS | Feature flag para activar/desactivar |
| R-08 | VIES downtime prolongado (>24h) | MEDIA | Optimistic breaker permite comercio con PENDING flag + background sweep | Aceptable. El Waiver delega riesgo al comprador |

## E.3. Gaps de Implementación Detectados

| # | Gap | Fase | Impacto | Acción requerida |
|---|-----|------|---------|-----------------|
| G-01 | Falta DPIA formal (Data Protection Impact Assessment) | Pre-producción | Bloqueante para tratamiento de PII de vendedores EU | Contratar DPO, completar DPIA antes de go-live |
| G-02 | Falta integración con pasarelas de pago reales (Stripe Connect test) | Fase 10 | Sin transacciones posibles | Crear cuenta Stripe Connect, implementar onboarding de sellers |
| G-03 | Falta pipeline de expiración automática de créditos | Fase 10 | Credits podrían no expirar correctamente | Implementar cron job que ejecute `OBJECT IDLE` scan en Redis |
| G-04 | Falta monitoring/alerting (Prometheus, Grafana) | Transversal | Sin observabilidad en producción | V2 Bloque 9 define la arquitectura. Implementar stack Prometheus + Grafana + Loki |
| G-05 | Falta CI/CD pipeline | Transversal | Deploys manuales, propensos a error | Implementar GitHub Actions → SSH deploy a nodos Hetzner |
| G-06 | Falta backup offsite automatizado | Fase 1 | RPO cumplido (WAL-G) pero sin offsite geográfico | Configurar WAL-G push a Hetzner Storage Box en DC diferente |
| G-07 | Falta rate limiting en QUIC Edge gateway | Fase 3 | Un Edge node comprometido podría inundar el pipeline | Implementar el token bucket Lua documentado en §3.2.2 |
| G-08 | Falta test de carga end-to-end | Transversal | Capacidad real desconocida | Diseñar load test con datos sintéticos (100K vehículos/hora) |
| G-09 | Falta contrato legal template para B2B webhooks | Fase 3 | Sin base contractual para Arval/BCA/LeasePlan | Redactar Data Sharing Agreement estándar |
| G-10 | Schema Watchdog no cubre ALTER TYPE ni DROP COLUMN | Fase 1 | DDL parciales podrían pasar sin detección | Ampliar hash a incluir column_default y is_nullable |

## E.4. Incoherencias Inter-Versión Resueltas

| # | Incoherencia | Versiones | Resolución canónica |
|---|-------------|-----------|-------------------|
| I-01 | V2 asume AWS Lambda + DynamoDB; V6 usa bare-metal | V2 vs V6 | V6 prevalece en infraestructura. V2 conceptos (multi-tenancy, RLS) se adaptan a PostgreSQL |
| I-02 | V2 usa GPT-3.5/GPT-4 via API; V6 usa local llama.cpp | V1/V2 vs V5/V6 | V6 prevalece. Cascade L1/L2/L3 local. Zero cloud AI dependency |
| I-03 | V2 pricing (Freemium/Pro/Enterprise) vs V6 Compute Credits | V2 vs V6 | Híbrido: planes V2 + créditos V6 con TTL Anti-MiCA |
| I-04 | V2 propone FAISS para vector search; V6 no lo menciona | V2 vs V6 | Eliminado. Redis HNSW (via RediSearch) para L2. Más simple, sin dependencia Python |
| I-05 | V5 usa Firecracker microVMs; V6 usa Bubblewrap | V5 vs V6 | V6 prevalece. Bubblewrap: 0µs overhead vs 300µs. Seccomp-BPF para syscall filtering |
| I-06 | V2 propone LangGraph multi-agent; V6 no lo implementa | V2 vs V6 | Descartado. La arquitectura de Redis Streams + workers especializados es más determinista y auditable que un framework agéntico |
| I-07 | V2 define "CARDEX Score" como ML model; V6 lo reduce a fórmula ponderada | V2 vs V6 | V6 prevalece para MVP. Score = weighted composite. ML scoring puede añadirse como L2/L3 futuro |
| I-08 | V1 propone multi-region AWS; V6 es single-DC Hetzner | V1 vs V6 | V6 prevalece. DR via WAL-G offsite + Dormant IPFS. Multi-DC es fase futura post-rentabilidad |

## E.5. Dependencias Circulares Identificadas

| Ciclo | Componentes | Resolución |
|-------|-------------|-----------|
| Fase 5 → Fase 2 → Fase 5 | Tax Hunter consulta L3 cache (dict:l1_tax) que es poblado por L3 Worker, que es alimentado por Tax Hunter cuando L1 miss | No es circular: es un feedback loop intencional. L3 Worker opera async. Tax Hunter no bloquea esperando resultado — marca PENDING y continúa. El resultado L3 se inyecta en L1 para consultas futuras |
| Fase 6 → Fase 7 → Fase 6 | Alpha Engine calcula NLC y publica. La reserva (Mutex en Fase 6) dispara Fase 7 (legal check). Si legal falla, el vehículo vuelve a ACTIVE en Fase 6 | No es circular: es un lifecycle lineal con rollback. El Mutex tiene TTL de 120s como circuit breaker |
| Fase 8 → Fase 6 → Fase 8 | Karma Engine (Fase 8) modifica throttling_tier que afecta la latencia del QUIC Gateway (Fase 6) | Correcto: es un side-effect unidireccional. Karma escribe, Gateway lee. Sin acoplamiento bidireccional |

---

## ESTADO FINAL DEL DOCUMENTO

**Sellado:** 2026-02-27  
**Autor:** Auditoría forense automatizada sobre corpus V1-V6 (924 páginas)  
**Régimen de prevalencia:**
- **Infraestructura y runbooks:** V6 prevalece. V5 complementa donde V6 no redefine.
- **Lógica de negocio, pricing, product design:** V2 prevalece. V6 Fase 10 complementa con estructura corporativa.
- **Elementos ilegales:** V4 purgado completamente. 10/10 elementos eliminados o sustituidos por alternativas legales (tabla E.1).
- **V1:** Descartado excepto conceptos de LLM orchestration adaptados a local inference.
- **V3:** Absorbido por V5/V6 (bare-metal pivot ya consolidado).

**Bloques completados:**
- [x] Fases 0-10 (Arquitectura de implementación, runbooks, código)
- [x] 10 Contradicciones resueltas con justificación técnica
- [x] Data Models (PostgreSQL DDL + ClickHouse DDL + Redis Key Schema)
- [x] Product Design (Mandato Vivo lifecycle, Vehicle lifecycle, Terminal UI)
- [x] Unit Economics (Pricing tiers, OPEX, break-even, proyección 36m)
- [x] Audit Forense (10 elementos ilegales purgados, 8 riesgos residuales, 10 gaps, 8 incoherencias, 3 dependencias circulares)
- [x] Mapa de Redis Streams end-to-end
- [x] Topología de nodos con asignación NUMA
- [x] Glosario institucional
- [x] 6 Propuestas de mejora inline

**Documento completo. Sin bloques pendientes.**

---

# BLOQUE II: DATA MODELS (DDL EJECUTABLE)

## A. POSTGRESQL 16 — OLTP (Nodo 01, ZFS, CCD0)

### A.1. Extensiones Requeridas

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";       -- UUIDv7 monotonic
CREATE EXTENSION IF NOT EXISTS "pgcrypto";         -- Encryption at field level
CREATE EXTENSION IF NOT EXISTS "pg_trgm";          -- Fuzzy text search
CREATE EXTENSION IF NOT EXISTS "btree_gist";       -- Exclusion constraints
CREATE EXTENSION IF NOT EXISTS "hstore";           -- Sparse metadata
```

### A.2. Tabla: entities (Dealers, Fleets, Instituciones)

```sql
CREATE TABLE entities (
    entity_ulid       TEXT PRIMARY KEY,                         -- ULIDv7 monotónico
    entity_type       TEXT NOT NULL CHECK (entity_type IN ('DEALER','FLEET','INSTITUTION','INDIVIDUAL')),
    legal_name        TEXT NOT NULL,                            -- Cifrado: Vault DEK envelope
    trade_name        TEXT,
    vat_id            TEXT,                                     -- Cifrado: Vault DEK envelope
    vat_validated     BOOLEAN DEFAULT FALSE,
    vat_last_check    TIMESTAMPTZ,
    country_code      CHAR(2) NOT NULL,                        -- ISO 3166-1 alpha-2
    h3_index_res4     TEXT,                                     -- Uber H3 sede principal
    contact_email     TEXT,                                     -- Cifrado: Vault DEK envelope
    contact_phone     TEXT,                                     -- Cifrado: Vault DEK envelope
    stripe_account_id TEXT,                                     -- Stripe Connect onboarding
    kyc_status        TEXT DEFAULT 'PENDING' CHECK (kyc_status IN ('PENDING','VERIFIED','REJECTED')),
    subscription_tier TEXT DEFAULT 'FREE' CHECK (subscription_tier IN ('FREE','PRO','CROSS_BORDER','INSTITUTIONAL')),
    karma_score       INT DEFAULT 100 CHECK (karma_score BETWEEN 0 AND 200),
    throttle_ms       INT DEFAULT 0,                           -- Latencia artificial (shadowban)
    onboarded_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    vault_dek_id      TEXT NOT NULL                             -- Referencia a Vault para crypto-shredding RGPD
) WITH (fillfactor = 70);

CREATE INDEX idx_entities_type ON entities (entity_type);
CREATE INDEX idx_entities_country ON entities (country_code);
CREATE INDEX idx_entities_h3 ON entities (h3_index_res4);
CREATE INDEX idx_entities_tier ON entities (subscription_tier);
```

### A.3. Tabla: mandates (Mandato Vivo — Unidad Atómica)

```sql
CREATE TABLE mandates (
    mandate_ulid      TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid),
    status            TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','PAUSED','FULFILLED','EXPIRED','CANCELLED')),
    -- Criterios de búsqueda (JSON estructurado)
    criteria          JSONB NOT NULL,
    -- Ejemplo criteria: {"makes":["BMW","AUDI"],"models":["Serie 5","A6"],"year_min":2019,"year_max":2023,
    --   "km_max":120000,"budget_max_eur":35000,"target_markets":["ES","FR"],
    --   "min_margin_pct":8.0,"max_risk_score":0.3,"tax_preference":"DEDUCTIBLE"}
    target_quantity   INT DEFAULT 1,
    fulfilled_count   INT DEFAULT 0,
    max_days_active   INT DEFAULT 90,
    alert_channels    TEXT[] DEFAULT ARRAY['PUSH','EMAIL'],     -- Canales de notificación
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    expires_at        TIMESTAMPTZ,
    last_match_at     TIMESTAMPTZ,
    updated_at        TIMESTAMPTZ DEFAULT NOW()
) WITH (fillfactor = 70);

CREATE INDEX idx_mandates_entity ON mandates (entity_ulid);
CREATE INDEX idx_mandates_status ON mandates (status) WHERE status = 'ACTIVE';
CREATE INDEX idx_mandates_criteria ON mandates USING GIN (criteria jsonb_path_ops);
```

### A.4. Tabla: vehicles (Inventario Activo)

```sql
CREATE TABLE vehicles (
    vehicle_ulid      TEXT PRIMARY KEY,
    fingerprint_sha256 TEXT UNIQUE NOT NULL,                    -- SHA-256(VIN + color_lower + mileage)
    vin               TEXT,                                     -- ISO 3779, 17 chars. Nullable (no siempre disponible)
    source_id         TEXT NOT NULL,                            -- ID en portal de origen
    source_platform   TEXT NOT NULL,                            -- 'BCA','ARVAL','MOBILE_DE','EDGE_FLEET',...
    ingestion_channel TEXT NOT NULL CHECK (ingestion_channel IN ('B2B_WEBHOOK','EDGE_FLEET','MANUAL')),

    -- Datos brutos
    make              TEXT,
    model             TEXT,
    variant           TEXT,
    year              INT,
    mileage_km        INT,
    color             TEXT,
    fuel_type         TEXT,
    transmission      TEXT,
    co2_gkm           INT,
    power_kw          INT,
    doors             INT,
    origin_country    CHAR(2),
    raw_description   TEXT,                                     -- Texto original del anuncio (multi-idioma)
    thumb_url         TEXT,

    -- Precios y costes (calculados por Pipeline Fase 4-6)
    price_raw         NUMERIC(12,2),                           -- Precio en divisa original
    currency_raw      CHAR(3),                                 -- ISO 4217
    gross_physical_cost_eur NUMERIC(12,2),                     -- Fase 4: precio + daños en EUR
    net_landed_cost_eur     NUMERIC(12,2),                     -- Fase 6: GPC + impuestos + logística
    logistics_cost_eur      NUMERIC(12,2),
    tax_amount_eur          NUMERIC(12,2),

    -- Scoring y estados
    tax_status        TEXT DEFAULT 'UNKNOWN' CHECK (tax_status IN
                      ('DEDUCTIBLE','REBU','REQUIRES_HUMAN_AUDIT','PENDING_VIES_OPTIMISTIC','UNKNOWN')),
    tax_confidence    NUMERIC(3,2),                            -- 0.00 a 1.00
    legal_status      TEXT DEFAULT 'UNCHECKED' CHECK (legal_status IN
                      ('UNCHECKED','LEGAL_CLEAR','LEGAL_LIEN_OR_STOLEN','FRAUD_ODOMETER_ROLLBACK',
                       'LEGAL_TIMEOUT','LEGAL_UNKNOWN')),
    risk_score        NUMERIC(3,2),                            -- 0.00 (safe) a 1.00 (danger)
    liquidity_score   NUMERIC(3,2),                            -- 0.00 (slow) a 1.00 (fast rotation)
    cardex_score      NUMERIC(5,2),                            -- Composite multidimensional score
    sdi_alert         BOOLEAN DEFAULT FALSE,                   -- Seller Desperation Index flag

    -- Geoespacial
    lat               NUMERIC(9,6),
    lng               NUMERIC(9,6),
    h3_index_res4     TEXT,
    h3_index_res7     TEXT,

    -- Lifecycle
    days_on_market    INT DEFAULT 0,
    first_seen_at     TIMESTAMPTZ DEFAULT NOW(),
    last_updated_at   TIMESTAMPTZ DEFAULT NOW(),
    sold_at           TIMESTAMPTZ,
    lifecycle_status  TEXT DEFAULT 'ACTIVE' CHECK (lifecycle_status IN
                      ('INGESTED','ENRICHED','MARKET_READY','RESERVED','SOLD','EXPIRED','FRAUD_BLOCKED')),

    -- HMAC Quote (Fase 6)
    current_quote_id  TEXT,
    quote_generated_at TIMESTAMPTZ,

    -- OCR
    extracted_vin     TEXT,                                     -- VIN extraído por OCR (Fase 5)
    ocr_confidence    NUMERIC(3,2)
) WITH (fillfactor = 70);

CREATE INDEX idx_vehicles_fingerprint ON vehicles (fingerprint_sha256);
CREATE INDEX idx_vehicles_vin ON vehicles (vin) WHERE vin IS NOT NULL;
CREATE INDEX idx_vehicles_source ON vehicles (source_platform);
CREATE INDEX idx_vehicles_lifecycle ON vehicles (lifecycle_status);
CREATE INDEX idx_vehicles_h3_4 ON vehicles (h3_index_res4);
CREATE INDEX idx_vehicles_h3_7 ON vehicles (h3_index_res7);
CREATE INDEX idx_vehicles_nlc ON vehicles (net_landed_cost_eur) WHERE lifecycle_status = 'MARKET_READY';
CREATE INDEX idx_vehicles_score ON vehicles (cardex_score DESC) WHERE lifecycle_status = 'MARKET_READY';
CREATE INDEX idx_vehicles_make_model ON vehicles (make, model);
CREATE INDEX idx_vehicles_tax ON vehicles (tax_status) WHERE tax_status IN ('REQUIRES_HUMAN_AUDIT','PENDING_VIES_OPTIMISTIC');
```

### A.5. Tabla: reservations (Mutex de Compra)

```sql
CREATE TABLE reservations (
    reservation_ulid  TEXT PRIMARY KEY,
    vehicle_ulid      TEXT NOT NULL REFERENCES vehicles(vehicle_ulid),
    buyer_entity_ulid TEXT NOT NULL REFERENCES entities(entity_ulid),
    quote_id_hmac     TEXT NOT NULL,                            -- HMAC-SHA256 del estado al reservar
    nlc_at_reservation NUMERIC(12,2) NOT NULL,
    status            TEXT NOT NULL DEFAULT 'LOCKED' CHECK (status IN
                      ('LOCKED','LEGAL_PENDING','CONFIRMED','EXPIRED','CANCELLED','PRICE_MISMATCH')),
    locked_at         TIMESTAMPTZ DEFAULT NOW(),
    lock_expires_at   TIMESTAMPTZ NOT NULL,                    -- NOW() + 120s
    legal_resolved_at TIMESTAMPTZ,
    confirmed_at      TIMESTAMPTZ,
    waiver_signed     BOOLEAN DEFAULT FALSE,                   -- Risk delegation si LEGAL_UNKNOWN
    stripe_payment_id TEXT,
    take_rate_eur     NUMERIC(8,2),
    CONSTRAINT uq_active_reservation EXCLUDE USING gist (
        vehicle_ulid WITH =
    ) WHERE (status IN ('LOCKED','LEGAL_PENDING'))
) WITH (fillfactor = 70);

CREATE INDEX idx_reservations_vehicle ON reservations (vehicle_ulid);
CREATE INDEX idx_reservations_buyer ON reservations (buyer_entity_ulid);
CREATE INDEX idx_reservations_status ON reservations (status) WHERE status IN ('LOCKED','LEGAL_PENDING');
```

### A.6. Tabla: subscriptions (Suscripciones y Billing)

```sql
CREATE TABLE subscriptions (
    subscription_ulid TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid),
    tier              TEXT NOT NULL CHECK (tier IN ('FREE','PRO','CROSS_BORDER','INSTITUTIONAL')),
    price_eur_month   NUMERIC(8,2) NOT NULL,
    billing_cycle     TEXT DEFAULT 'MONTHLY' CHECK (billing_cycle IN ('MONTHLY','ANNUAL')),
    stripe_sub_id     TEXT,
    started_at        TIMESTAMPTZ DEFAULT NOW(),
    current_period_end TIMESTAMPTZ,
    cancelled_at      TIMESTAMPTZ,
    status            TEXT DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','PAST_DUE','CANCELLED','TRIALING'))
) WITH (fillfactor = 70);

CREATE INDEX idx_subscriptions_entity ON subscriptions (entity_ulid);
```

### A.7. Tabla: compute_credits (Anti-MiCA, TTL 90d)

```sql
CREATE TABLE compute_credits (
    credit_ulid       TEXT PRIMARY KEY,
    entity_ulid       TEXT NOT NULL REFERENCES entities(entity_ulid),
    amount            INT NOT NULL,                            -- Créditos comprados
    remaining         INT NOT NULL,
    purchased_at      TIMESTAMPTZ DEFAULT NOW(),
    expires_at        TIMESTAMPTZ NOT NULL,                    -- purchased_at + INTERVAL '90 days'
    stripe_charge_id  TEXT,
    CONSTRAINT chk_expires CHECK (expires_at = purchased_at + INTERVAL '90 days'),
    CONSTRAINT chk_remaining CHECK (remaining >= 0 AND remaining <= amount)
) WITH (fillfactor = 70);

CREATE INDEX idx_credits_entity ON compute_credits (entity_ulid);
CREATE INDEX idx_credits_expiry ON compute_credits (expires_at) WHERE remaining > 0;
```

### A.8. Vista Filtrada para Zero-PII ClickHouse Replication

```sql
CREATE VIEW vehicles_no_pii AS
SELECT
    vehicle_ulid, fingerprint_sha256, source_platform, ingestion_channel,
    make, model, variant, year, mileage_km, color, fuel_type, transmission,
    co2_gkm, power_kw, origin_country,
    price_raw, currency_raw, gross_physical_cost_eur, net_landed_cost_eur,
    logistics_cost_eur, tax_amount_eur,
    tax_status, tax_confidence, legal_status, risk_score, liquidity_score,
    cardex_score, sdi_alert,
    h3_index_res4, h3_index_res7, days_on_market,
    first_seen_at, last_updated_at, sold_at, lifecycle_status
FROM vehicles;

-- Publication para MaterializedPostgreSQL (Zero-PII enforcement)
CREATE PUBLICATION cardex_analytics_pub FOR TABLE vehicles_no_pii;
```

## B. CLICKHOUSE — OLAP (Nodo 01/05, XFS Direct I/O, CCD0)

### B.1. Base de Datos y Tablas

```sql
CREATE DATABASE IF NOT EXISTS cardex;
CREATE DATABASE IF NOT EXISTS cardex_forensics;

-- Inventario analítico (replicado desde PostgreSQL Zero-PII view)
CREATE TABLE cardex.vehicle_inventory (
    vehicle_ulid      String,
    fingerprint_sha256 String,
    source_platform   LowCardinality(String),
    ingestion_channel LowCardinality(String),
    make              LowCardinality(String),
    model             LowCardinality(String),
    variant           String,
    year              UInt16,
    mileage_km        UInt32,
    color             LowCardinality(String),
    fuel_type         LowCardinality(String),
    transmission      LowCardinality(String),
    co2_gkm           UInt16,
    power_kw          UInt16,
    origin_country    LowCardinality(FixedString(2)),
    price_raw         Float64,
    currency_raw      FixedString(3),
    gross_physical_cost_eur Float64,
    net_landed_cost_eur     Float64,
    logistics_cost_eur      Float64,
    tax_amount_eur          Float64,
    tax_status        LowCardinality(String),
    tax_confidence    Float32,
    legal_status      LowCardinality(String),
    risk_score        Float32,
    liquidity_score   Float32,
    cardex_score      Float32,
    sdi_alert         UInt8,
    h3_index_res4     String,
    h3_index_res7     String,
    days_on_market    UInt16,
    first_seen_at     DateTime64(3),
    last_updated_at   DateTime64(3),
    sold_at           Nullable(DateTime64(3)),
    lifecycle_status  LowCardinality(String)
) ENGINE = ReplacingMergeTree(last_updated_at)
ORDER BY (make, model, vehicle_ulid)
PARTITION BY toYYYYMM(first_seen_at)
TTL first_seen_at + INTERVAL 2 YEAR DELETE
SETTINGS index_granularity = 8192;

-- Histórico forense de kilometrajes (Odometer Rollback Detection)
CREATE TABLE cardex_forensics.mileage_history (
    vin             String,
    recorded_date   Date,
    mileage         UInt32,
    country         LowCardinality(String),
    source          LowCardinality(String),    -- 'B2B_FEED','EDGE_FLEET','CARFAX','IDEAUTO'
    ingested_at     DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (vin, recorded_date)
PARTITION BY toYYYYMM(recorded_date)
SETTINGS index_granularity = 8192;

-- Bóveda de siniestros (Licensed B2B feeds)
CREATE TABLE cardex_forensics.salvage_ledger (
    vin             String,
    event_date      Date,
    event_type      LowCardinality(String),    -- 'TOTAL_LOSS','STRUCTURAL','FLOOD','THEFT_RECOVERED'
    severity        LowCardinality(String),    -- 'MINOR','MODERATE','SEVERE'
    source          LowCardinality(String),    -- 'CARFAX','AUTODNA','INTERNAL'
    country         LowCardinality(String),
    description     String,
    ingested_at     DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (vin, event_date)
PARTITION BY toYYYYMM(event_date);

-- Índice de precios agregado (CARDEX Index)
CREATE TABLE cardex.price_index (
    index_date      Date,
    make            LowCardinality(String),
    model           LowCardinality(String),
    country         LowCardinality(FixedString(2)),
    h3_res4         String,
    avg_nlc_eur     Float64,
    median_nlc_eur  Float64,
    p10_nlc_eur     Float64,
    p90_nlc_eur     Float64,
    volume          UInt32,
    avg_days_on_market Float32,
    computed_at     DateTime DEFAULT now()
) ENGINE = SummingMergeTree()
ORDER BY (index_date, make, model, country)
PARTITION BY toYYYYMM(index_date);
```

## C. REDIS — ESQUEMA DE CLAVES

```
# Streams (Fase 3-8)
stream:ingestion_raw          # Payloads crudos del Gateway
stream:db_write               # Vehículos post-pipeline hacia Tax Hunter
stream:visual_audit           # Fotos para OCR (MaxLenApprox: 1000)
stream:l3_pending             # Solicitudes de inferencia L3
stream:market_ready           # Vehículos listos para pricing
stream:market_pricing         # Hacia Alpha Engine
stream:legal_audit_pending    # VINs pendientes de verificación oficial
stream:forensic_updates       # VINs extraídos por OCR
stream:operator_events        # Eventos de karma (reservas expiradas/confirmadas)

# Hashes
dict:l1_tax                   # Cache L1 de clasificaciones fiscales: {vehicle_id → JSON}
vehicle_state:<hash>          # Estado en RAM: {quote_id, vin, mileage, legal_status}
fx_buffer                     # Oráculo FX: {currency_code → EUR_multiplier}
logistics:worst_case          # Logística pessimista: {country_code → EUR_cost}
b2b_rosetta:<SOURCE>          # Mapeo de damage codes por fuente
throttling_tier               # Shadowban: {buyer_id → ms_adicionales}

# Keys simples
lock:<vehicle_hash>           # Mutex atómico (TTL 120s)
karma:<buyer_id>              # Score de karma (INT, 0-200)
bloom:vehicles                # RedisBloom filter (50M capacity, 0.01% FP rate)
credits:<entity_ulid>         # Saldo de créditos (TTL 90d via Lua)

# Consumer Groups
cg_pipeline                   # Pipeline HFT workers
cg_forensics                  # Tax Hunter workers
cg_ocr_workers                # OCR workers
cg_qwen_workers               # L3 IA workers
cg_alpha                      # Alpha Engine workers
cg_gov                        # Legal Hub workers
cg_karma                      # Karma Engine workers

# Pub/Sub
channel:live_market           # Fan-out SSE para terminales B2B
```

---

# BLOQUE III: PRODUCT DESIGN

## A. MANDATO VIVO — UNIDAD ATÓMICA DEL ECOSISTEMA

### A.1. Definición

El Mandato es una orden de búsqueda y compra persistente y algorítmica. A diferencia de una búsqueda puntual, el Mandato es un proceso vivo: el sistema trabaja contra él 24/7, escaneando todo el inventario entrante y notificando al operador cuando surge un match que cumple sus criterios de make/model, presupuesto, margen mínimo, riesgo máximo y mercados destino.

### A.2. Lifecycle del Mandato

```
CREATED → ACTIVE → [PAUSED] → FULFILLED | EXPIRED | CANCELLED
                      ↑  ↓
                    (toggle)
```

| Estado | Trigger | Efecto |
|--------|---------|--------|
| ACTIVE | Creación o reanudación | Matching engine evalúa cada vehículo nuevo contra criteria JSONB |
| PAUSED | Operador pausa manualmente | Se deja de evaluar. No consume créditos |
| FULFILLED | fulfilled_count ≥ target_quantity | Mandato completado. Se genera Informe de Mandato PDF |
| EXPIRED | NOW() > expires_at (max 90d) | Cierre automático. Notificación al operador |
| CANCELLED | Operador cancela | Cierre inmediato |

### A.3. Matching Engine (Hot Path)

Cada vehículo que entra en `stream:market_ready` se evalúa contra todos los mandatos ACTIVE:

```
Para cada mandate ACTIVE:
  1. Filtro determinista: make ∈ criteria.makes AND year ∈ [min,max] AND km ≤ max AND NLC ≤ budget
  2. Si pasa filtro: Calcular encaje (match_score) = f(price_fit, liquidity, risk, margin_potential)
  3. Si match_score > threshold (configurable por tier): Emitir Oportunidad Priorizada
  4. Notificar por alert_channels
```

El matching se ejecuta en Redis Lua para evitar round-trips. Los mandatos ACTIVE se cachean en un hash `mandates:active:<entity_ulid>` con TTL de refresh cada 60s desde PostgreSQL.

### A.4. Outputs Derivados del Mandato

| Output | Formato | Trigger |
|--------|---------|---------|
| Oportunidad Priorizada | Push notification + entrada en dashboard | Match automático |
| Informe de Mandato | PDF institucional (generado por Fase 2 L3) | Solicitud manual o FULFILLED |
| Trade Ticket | PDF + registro en BD + trigger Stripe | Confirmación de compra |
| CARDEX Dossier | Dashboard interactivo + exportable PDF | Click en vehículo específico |

## B. LIFECYCLE DEL VEHÍCULO (END-TO-END)

```
[Fuente B2B / Edge Fleet]
        │
        ▼
    INGESTED ──── Fase 3: Gateway acepta, inyecta en stream:ingestion_raw
        │
        ▼
    ENRICHED ──── Fase 4: Deduplicado (Bloom), H3 sharding, GPC calculado
        │              Fase 5: Tax classification, OCR VIN, VIES check
        ▼
  MARKET_READY ── Fase 6: NLC calculado, Quote HMAC generado, SDI evaluado
        │              Matching engine cruza contra mandatos ACTIVE
        │              Fan-out SSE a terminales B2B
        ▼
   RESERVED ───── Fase 6: Lua Mutex locks 120s. Escrow lógico iniciado
        │              Fase 7: Consulta legal asíncrona (IDEAUTO/CARFAX)
        ├── LEGAL_CLEAR ────→ SOLD (Stripe split payment ejecutado)
        ├── FRAUD_BLOCKED ──→ Bloqueo permanente (odometer/stolen)
        ├── LEGAL_TIMEOUT ──→ Waiver obligatorio → SOLD con flag LEGAL_UNKNOWN
        └── Lock expirado ──→ Karma -15. Vehículo vuelve a MARKET_READY
        
    EXPIRED ──── days_on_market > 180: Archivado en ClickHouse, eliminado de RAM
```

## C. INTERFAZ TERMINAL B2B (Dark Pool)

### C.1. Arquitectura de Rendering

```
[QUIC SSE stream:market_ready]
        │
        ▼
  [Web Worker: WASM OrderBook]
        │ Decomprime, ordena por NLC, filtra por mandatos
        │ Emite JSON con 30 elementos visibles
        ▼
  [Main Thread: Virtual Scroller]
        │ Recicla 30 nodos DOM
        │ Actualiza campos reactivamente
        ▼
  [UI: 120 FPS, texto seleccionable, Ctrl+C funcional]
```

### C.2. Paneles del Terminal

| Panel | Contenido | Fuente de datos |
|-------|-----------|-----------------|
| Radar de Oportunidades | Grid virtual ordenable por NLC/Score/SDI | WASM OrderBook (QUIC live) |
| Mandatos Activos | Lista de mandatos con progress bar y match count | PostgreSQL via REST |
| Dossier de Vehículo | Ficha completa: scoring, historial, fotos, cálculos | PostgreSQL + ClickHouse |
| CARDEX Index | Gráficas de tendencias de precios por make/model/país | ClickHouse price_index |
| Trade Execution | Botón Reservar → Quote validation → Legal check → Stripe | Redis Lua Mutex → API |

---

# BLOQUE IV: UNIT ECONOMICS Y PRICING

## A. ESTRUCTURA DE TIERS

| Tier | Precio/mes | Target | Incluye |
|------|-----------|--------|---------|
| FREE | 0€ | Cualquier usuario | 2 búsquedas/día, 1 mercado, alertas semanales, 50 créditos bienvenida |
| PRO | 299€ | Microdealers, dealers locales | Nacional ilimitado, 5 mercados, alertas diarias, 500 créditos/mes, filtros IA, 3 usuarios |
| CROSS-BORDER | 599€ | Dealers paneuropeos | Pan-UE ilimitado, alertas real-time, 2000 créditos/mes, Mandatos ilimitados, Dossiers PDF, 10 usuarios |
| INSTITUCIONAL | 1.499€ | Grandes grupos, flotas, financieras | Todo ilimitado, API dedicada, CARDEX Index, SLA 99.9%, 50 usuarios, soporte dedicado |

Descuento anual: equivalente a 10 meses (ahorro ~17%).

## B. INGRESOS POR TRANSACCIÓN

| Concepto | Tarifa | Trigger |
|----------|--------|---------|
| Take-Rate por vehículo vendido | 250-300€ fijo o ~1% del valor | Stripe split payment en reserva confirmada |
| Consulta historial VIN (CARFAX/IDEAUTO) | Coste B2B (1-3€) + margen 300% → 3-9€ al cliente | Consumo de créditos o incluido en tier |
| Informe Dossier Premium (B2C) | 9.99-19.99€ | Pago puntual |
| Oráculo JWS (certificado de riesgo para bancos) | 5-15 BPS sobre valor colateral | API call institucional |
| Logística facilitada (transporte) | 5-10% margen sobre coste transportista | Servicio complementario |
| Licenciamiento de datasets (futuro) | Contrato a medida (50k-500k€/año) | Masa crítica de datos alcanzada |

## C. COSTES OPERATIVOS MENSUALES (STEADY-STATE, 3 NODOS)

| Partida | Coste/mes | Notas |
|---------|-----------|-------|
| Hetzner AX102 × 3 nodos | 3 × 89€ = 267€ | Bare-metal, no cloud. Incluye 1Gbps unmetered |
| Hetzner Storage Box (backups) | 50€ | S3-compatible para WAL-G PITR |
| Cloudflare Pro + Workers | 45€ | CDN, DNS, TLS, Edge SEO |
| Twilio DIDs + SIP (5 países) | ~200€ | Números locales ES/DE/FR/NL/IT |
| APIs B2B licenciadas (IDEAUTO, CARFAX feeds) | ~500-2000€ | Escala con reservas confirmadas |
| EV Code Signing certificate | ~33€ (400€/año) | Token USB HSM |
| Dominio + miscelánea | ~50€ | DNS, monitoring |
| **TOTAL OPEX infraestructura** | **~650-2.650€/mes** | Excluye salarios |

## D. UNIT ECONOMICS POR VEHÍCULO

```
Coste de procesar 1 vehículo end-to-end:
  Ingesta + deduplicación (Bloom)       ~0.0001€  (RAM, amortizado)
  Pipeline HFT + H3 sharding            ~0.0005€  (CPU, amortizado)
  Tax classification (L1 cache hit)      ~0.0001€  (Redis)
  Tax classification (L3 inference)      ~0.02€    (CPU Qwen2.5, ~3s)
  OCR (si tiene foto)                    ~0.005€   (ONNX, 2 threads)
  NLC calculation                        ~0.0001€  (RAM)
  ──────────────────────────────────
  TOTAL por vehículo (warm cache):       ~0.001€
  TOTAL por vehículo (cold, L3 + OCR):   ~0.025€

Coste de 1 reserva confirmada:
  Consulta legal B2B (IDEAUTO)           1-3€
  Lua Mutex + Quote verification         ~0€ (RAM)
  Stripe fee (1.4% + 0.25€)             ~281€ en vehículo de 20.000€
  ──────────────────────────────────
  TOTAL por reserva:                     ~284€

Ingreso por reserva:
  Take-Rate:                             300€
  ──────────────────────────────────
  Margen bruto por transacción:          ~16€ (5.3%)
  (Nota: el margen transaccional es bajo intencionalmente.
   La rentabilidad viene de las suscripciones recurrentes.)
```

## E. BREAK-EVEN Y PROYECCIÓN 36 MESES

### Supuestos conservadores:

| Métrica | M1-6 | M7-12 | M13-24 | M25-36 |
|---------|------|-------|--------|--------|
| Clientes PRO | 5 | 20 | 80 | 200 |
| Clientes CROSS-BORDER | 2 | 10 | 40 | 100 |
| Clientes INSTITUCIONAL | 0 | 2 | 8 | 20 |
| Transacciones/mes | 10 | 50 | 300 | 1.500 |
| OPEX infra/mes | 1.500€ | 2.000€ | 3.500€ | 5.000€ |
| OPEX personal (2→5→10 FTE) | 12.000€ | 20.000€ | 40.000€ | 70.000€ |

### Proyección de ingresos:

| Línea | M6 | M12 | M24 | M36 |
|-------|-----|------|------|------|
| Suscripciones | 2.693€ | 11.968€ | 47.880€ | 119.700€ |
| Transacciones (Take-Rate) | 3.000€ | 15.000€ | 90.000€ | 450.000€ |
| Créditos + Dossiers | 500€ | 3.000€ | 15.000€ | 50.000€ |
| Oráculos JWS | 0€ | 1.000€ | 10.000€ | 40.000€ |
| **TOTAL revenue/mes** | **6.193€** | **30.968€** | **162.880€** | **659.700€** |
| **TOTAL costes/mes** | **13.500€** | **22.000€** | **43.500€** | **75.000€** |
| **EBITDA/mes** | **-7.307€** | **+8.968€** | **+119.380€** | **+584.700€** |

**Break-even operativo:** Mes 10-11 (con 30+ clientes de pago y ~50 transacciones/mes).

### Métricas SaaS clave (M36 target):

| Métrica | Target |
|---------|--------|
| ARPU (blended) | ~375€/mes |
| Churn mensual | <3% |
| LTV (5 años, 3% churn) | ~12.500€ |
| CAC (blended) | <1.500€ |
| LTV/CAC | >8x |
| Gross Margin (suscripciones) | >85% |
| Gross Margin (transacciones) | ~5% (intencionalmente bajo para generar volumen) |

---

# BLOQUE V: AUDITORÍA FORENSE FORMAL

## A. REGISTRO DE CONTRADICCIONES INTER-VERSIÓN (AMPLIADO)

| ID | Versión(es) | Contradicción | Resolución Canónica | Riesgo Residual |
|----|-------------|---------------|---------------------|-----------------|
| C-01 | V4/V5 vs V6 | Thermal: PBO 95°C vs PPT 105W estricto | V6: RyzenAdj PPT=105W. Clock stretching inaceptable | Ninguno |
| C-02 | V3/V4 vs V6 | Sandboxing: Firecracker (~300µs) vs Bubblewrap (0µs) | V6: Bubblewrap + Seccomp | Ninguno |
| C-03 | V3 vs V6 | AVX-512: habilitado vs purgado | V6: `-mno-avx512f`. Double-pump Zen4 no justifica coste térmico | Throughput pico 8% menor. Aceptable |
| C-04 | V4 vs V6 | Scraping ilegal vs B2B licenciado | V6: Webhooks B2B + Edge delegado EU Data Act. V4 PURGADO | Legal: depende de volumen de acuerdos B2B cerrados |
| C-05 | V4 vs V6 | Caller ID spoofing vs Twilio DIDs | V6: STIR/SHAKEN compliance. V4 PURGADO | Ninguno |
| C-06 | V1 vs V3-V6 | AWS/cloud vs bare-metal | V3-V6: Hetzner bare-metal. V1 cloud architecture descartada | Single-vendor risk Hetzner |
| C-07 | V1 vs V6 | GPT-4 cloud vs Qwen2.5 local | V6: Inferencia local zero-cloud. Cache cascade L1/L2/L3 | Calidad de inferencia menor que GPT-4 en edge cases |
| C-08 | V1 vs V6 | SaaS flat pricing vs Compute Credits | V6: Credits con TTL 90d (Anti-MiCA) + suscripción tiered | Complejidad de billing |
| C-09 | V3 vs V6 | MaterializedPostgreSQL sin protección vs Schema Watchdog | V6: Watchdog obligatorio. Pausa replicación ante DDL | False positive puede pausar analytics innecesariamente |
| C-10 | V4 vs V6 | Slashing financiero vs Karma reputacional | V6: Shadow banning (+latencia). Zero chargebacks | Operador puede crear cuentas nuevas para evadir karma |

## B. ELEMENTOS ILEGALES PURGADOS DE V4 (REGISTRO EXPLÍCITO)

Los siguientes elementos de V4 han sido permanentemente eliminados del corpus canónico por constituir actividades ilegales bajo legislación EU:

| Elemento V4 | Artículo legal violado | Sustitución V6 |
|-------------|----------------------|-----------------|
| SSL Unpinning (Frida/ReDroid) | Art. 6 Directiva 2013/40/UE (acceso ilícito a sistemas) | Webhooks B2B autenticados HMAC |
| API Spoofing / Ghost Requests | Art. 197 CP (ES), CFAA §1030 (US) | APIs oficiales de pago (IDEAUTO, CARFAX) |
| Dark Web scraping (subastas ocultas) | Art. 270bis CP (IT), Data Protection Acts | Sindicación B2B con CARFAX/AutoDNA |
| Caller ID Spoofing | Art. 248 CP (ES), EU Telecom Act | Twilio DIDs legales con KYC corporativo |
| Emulación Android headless (ReDroid) | ToS violation + posible Art. 6 Dir. 2013/40 | Edge WebView2 nativo (Tauri) |
| DGT API Ghosting (suplantación) | Art. 248/249 CP (ES) | IDEAUTO API B2B de pago |
| Speedtest ocultos en PC cliente | Posible violación de expectativa razonable de uso | Passive TCP Backpressure (socket RTT) |

## C. GAPS DE IMPLEMENTACIÓN DETECTADOS

| ID | Gap | Criticidad | Fases afectadas | Recomendación |
|----|-----|-----------|-----------------|---------------|
| G-01 | No hay Circuit Breaker formal para APIs B2B externas | ALTA | 7 | Implementar Resilience4j o Polly pattern con half-open state |
| G-02 | Schema Watchdog no tiene tests de integración documentados | MEDIA | 1 | Crear test suite que simule DDL mutations y verifique pausa/resume |
| G-03 | L3 Worker es bash script, no servicio robusto | MEDIA | 2 | Reescribir en Go o Python con retry logic y dead letter queue |
| G-04 | No hay rate limiting en el Gateway HTTPS (solo eBPF para UDP) | ALTA | 3 | Añadir token bucket por IP + por entity en el handler Go |
| G-05 | Karma Engine no persiste en PostgreSQL | MEDIA | 8 | Añadir write-behind a tabla entities.karma_score cada 60s |
| G-06 | No hay monitoring/alerting stack definido | ALTA | Todas | Prometheus + Grafana + AlertManager en Nodo 01 |
| G-07 | Backup de Redis no documentado | ALTA | Todas | RDB snapshots cada 1h + AOF fsync everysec. Backup a S3 |
| G-08 | No hay runbook de Disaster Recovery completo | ALTA | Todas | Documentar RTO/RPO por componente y procedimiento de failover |
| G-09 | QUIC Gateway usa snakeoil certs | MEDIA | 3,6 | Let's Encrypt o ZeroSSL con auto-renewal |
| G-10 | No hay test de carga documentado (cómo validar 10M vehículos/día) | MEDIA | 4 | Crear script de load testing con datos sintéticos |
| G-11 | Matching engine Mandato→Vehículo no tiene benchmark de latencia | MEDIA | Producto | Definir SLO: matching < 100ms para 1000 mandatos activos |
| G-12 | Falta runbook de rotación de claves (Vault DEK, Ed25519, HMAC) | ALTA | 1,3,6 | Documentar procedimiento semestral con zero-downtime rotation |

## D. FÓRMULAS NO VALIDADAS / RIESGOS DE CÁLCULO

| Fórmula | Fase | Riesgo | Mitigación |
|---------|------|--------|------------|
| IEDMT España (CO₂ → %) | 6 | Tramos pueden cambiar por legislación autonómica | Externalizar tabla en Redis hash actualizable sin redeploy |
| Malus Écologique Francia | 6 | Fórmula cuadrática puede no reflejar baremo 2026 | Verificar contra service-public.fr anualmente |
| Rest-BPM Holanda | 6 | Depreciación forfaitaria puede cambiar | Verificar contra belastingdienst.nl |
| SDI thresholds (60/90 días) | 6 | Ciclos de floorplan varían por país y entidad financiera | Parametrizar umbrales por país en Redis hash |
| Bloom filter FP rate (0.01%) | 4 | A 100M entries, FP rate crece. Capacidad debe monitorizarse | Alertar si `BF.INFO bloom:vehicles` > 80% capacity |
| VIES timeout 200ms | 5 | Demasiado agresivo para algunos países (IT, ES) | Implementar timeout adaptativo por country_code |

## E. DEPENDENCIAS CIRCULARES Y ACOPLAMIENTO

| Dependencia | Componentes | Riesgo | Mitigación |
|------------|-------------|--------|------------|
| Redis es SPOF | Todas las fases | Caída de Redis = caída total | Redis Sentinel con 3 nodos (M1: implementar) |
| PostgreSQL → ClickHouse WAL | Fase 1 | DDL mutation rompe replicación | Schema Watchdog (ya implementado) |
| Fase 5 depende de Fase 2 (L3) | Tax Hunter → Qwen Worker | L3 caída = todos los vehículos nuevos van a HUMAN_AUDIT | Aceptable como degradación graceful |
| Fase 7 depende de APIs externas | Legal Hub → IDEAUTO/CARFAX | API caída = LEGAL_TIMEOUT (waiver) | Aceptable con risk delegation |
| Fase 8 depende de Fase 6 (Quote) | Terminal → Alpha Engine | Quote expirado = PRICE_MISMATCH | Refresh automático cada 30s en frontend |
| Karma en Redis sin persistencia | Fase 8 | Redis flush = karma reset | G-05: write-behind a PostgreSQL |

## F. VEREDICTO FINAL DEL AUDITOR

El corpus V1-V6 (924 páginas) contiene una arquitectura viable para una plataforma B2B de arbitraje de vehículos usados paneuropeos. La evolución de V1 (SaaS cloud genérico) a V6 (bare-metal determinista, legally compliant) demuestra maduración técnica significativa.

**Fortalezas confirmadas:** La arquitectura bare-metal con NUMA-aware pinning, el pipeline event-driven via Redis Streams, el modelo probabilístico Fail-Closed para clasificación fiscal, el Zero-Custody PSD2 via Stripe Connect, y la estructura Anti-MiCA de Compute Credits son decisiones técnicamente sólidas y legalmente defensibles.

**Riesgos principales:** Redis como SPOF (sin Sentinel), ausencia de monitoring stack, fórmulas fiscales hardcodeadas sin mecanismo de actualización dinámica, y dependencia de volumen de acuerdos B2B para sustituir la ingesta que antes proporcionaba el scraping ilegal.

**Recomendación:** El documento es ejecutable en su estado actual para un MVP con 3 nodos Hetzner. Los 12 gaps identificados en la Sección C deben priorizarse como sprint de hardening post-MVP, con G-06 (monitoring), G-07 (Redis backup), G-08 (DR runbook) y G-12 (key rotation) como bloqueantes antes de producción con datos reales.

---

**FIN DEL DOCUMENTO CANÓNICO**

Líneas totales: ~2.800  
Sellado: 2026-02-27  
Corpus fuente: V1 (386p) + V2 (292p) + V3 (74p) + V4 (32p) + V5 (91p) + V6 (49p) = 924 páginas  
Régimen de prevalencia: V6 (implementación) > V2 (negocio/producto) > V5 (runbooks) > V3 (infra base) > V1 (descartado) > V4 (purgado)
