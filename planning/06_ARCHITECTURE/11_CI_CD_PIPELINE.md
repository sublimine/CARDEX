# 11 — CI/CD Pipeline

## Identificador
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Principios

1. **Illegal pattern linter es gate bloqueante** — ningún commit que contenga técnicas de evasión (C-04/C-10 en ILLEGAL_CODE_PURGE_PLAN.md) puede pasar al deploy bajo ninguna circunstancia
2. **Deploy in-place, no containers** — los servicios Go se despliegan como binarios via rsync + systemctl restart; sin downtime de servicios no modificados
3. **Ventana de deploy restringida** — 03:00-05:00 CET (fuera de ventana NLG 00:30-06:00 y fuera de horario de uso B2B)
4. **Self-hosted** — Forgejo en el propio VPS; el código fuente nunca abandona la infraestructura controlada
5. **Tests gates obligatorios** — coverage mínimo 70% en packages críticos; integración sobre dataset de muestra real

---

## Forgejo — Configuración self-hosted

```
Deployado en: Docker Compose en VPS (ver 07_DEPLOYMENT_TOPOLOGY.md)
URL interna:  http://localhost:3002 (acceso solo via SSH tunnel)
SSH Git:      localhost:2222
Organización: cardex
Repositorio:  cardex/cardex (privado)
Rama default: main
Branch protection:
  - main: require pull request, require CI pass, no force push
  - claude/*: CI requerido, merge sin aprobación (worktrees de agentes)
```

### Webhook configuration
```
Event:   push, pull_request
Target:  http://localhost:3002/api/v1/repos/cardex/cardex/hooks
Secret:  HMAC-SHA256 verificado en runner
Runner:  Forgejo Act Runner (self-hosted, mismo VPS)
```

---

## Pipeline Completo — `.forgejo/workflows/ci.yml`

```yaml
name: CARDEX CI/CD Pipeline
on:
  push:
    branches: ['main', 'claude/*', 'feature/*']
  pull_request:
    branches: ['main']

env:
  GO_VERSION: '1.22'
  GOLANGCI_VERSION: 'v1.57.2'

jobs:
  # ═══════════════════════════════════════════════════════
  # STEP 1 — Lint (Go + Python)
  # ═══════════════════════════════════════════════════════
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Go
        uses: actions/setup-go@v5
        with:
          go-version: ${{ env.GO_VERSION }}
          cache: true

      - name: golangci-lint
        uses: golangci/golangci-lint-action@v4
        with:
          version: ${{ env.GOLANGCI_VERSION }}
          args: --timeout=5m --config=.golangci.yml

      - name: Go vet
        run: go vet ./...

      - name: Python lint (flake8 + black check)
        working-directory: ./python
        run: |
          pip install flake8 black
          flake8 . --max-line-length=120
          black --check .

  # ═══════════════════════════════════════════════════════
  # STEP 2 — ILLEGAL PATTERN SCAN (GATE BLOQUEANTE)
  # ═══════════════════════════════════════════════════════
  illegal-pattern-scan:
    name: Illegal Pattern Scan (BLOCKING)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # full history para scan completo

      - name: Scan Go source for illegal patterns
        run: |
          set -euo pipefail
          VIOLATIONS=0

          # Lista completa de patrones ilegales (C-04 y C-10)
          # Ver ILLEGAL_CODE_PURGE_PLAN.md para justificación completa
          declare -A ILLEGAL_PATTERNS=(
            # TLS fingerprint evasion
            ["curl_cffi"]="TLS fingerprint evasion library"
            ["CycleTLS"]="JA3/JA4 fingerprint evasion"
            ["tls-client.*bogdanfinn"]="TLS evasion library"
            ["utls.*refraction"]="uTLS TLS fingerprint spoofing"
            ["JA3Fingerprint"]="JA3 fingerprint manipulation"
            ["JA4Fingerprint"]="JA4 fingerprint manipulation"

            # Browser stealth
            ["playwright-stealth"]="Browser stealth / bot detection evasion"
            ["stealth.*playwright"]="Browser stealth plugin"
            ["puppeteer-extra-plugin-stealth"]="Puppeteer stealth"
            ["useAutomationExtension.*false"]="Chrome automation flag evasion"
            ["excludeSwitches.*enable-automation"]="Chrome automation flag removal"
            ["webdriver.*undefined"]="WebDriver fingerprint spoofing"

            # Proxy evasion
            ["residential.*proxy"]="Residential proxy (IP evasion)"
            ["rotating.*proxy"]="Rotating proxy (IP evasion)"
            ["bright.*data"]="BrightData residential proxy"
            ["oxylabs"]="Oxylabs residential proxy"
            ["smartproxy"]="SmartProxy residential proxy"

            # User-Agent spoofing
            ["fakeUserAgent"]="Fake user agent library"
            ["random.*user.agent"]="Random user agent rotation"
          )

          echo "=== CARDEX Illegal Pattern Scan ==="
          echo "Scanning $(find . -name '*.go' -o -name '*.py' -o -name '*.js' | wc -l) source files..."

          for pattern in "${!ILLEGAL_PATTERNS[@]}"; do
            description="${ILLEGAL_PATTERNS[$pattern]}"
            matches=$(grep -rn --include="*.go" --include="*.py" --include="*.js" \
                      --include="*.ts" --include="go.mod" --include="go.sum" \
                      --include="requirements*.txt" --include="package.json" \
                      -i "$pattern" . 2>/dev/null || true)

            if [ -n "$matches" ]; then
              echo ""
              echo "❌ ILLEGAL PATTERN DETECTED: $pattern"
              echo "   Reason: $description"
              echo "   Occurrences:"
              echo "$matches" | head -20
              VIOLATIONS=$((VIOLATIONS + 1))
            fi
          done

          # Verificar que CardexBot UA está presente (no ausente) en crawlers
          BOT_UA_COUNT=$(grep -rn "CardexBot" --include="*.go" . | wc -l)
          if [ "$BOT_UA_COUNT" -lt 1 ]; then
            echo ""
            echo "⚠️  WARNING: CardexBot/1.0 User-Agent not found in Go source"
            echo "   All HTTP clients must identify as CardexBot/1.0"
          fi

          echo ""
          echo "=== Scan complete: $VIOLATIONS violation(s) found ==="

          if [ "$VIOLATIONS" -gt 0 ]; then
            echo ""
            echo "════════════════════════════════════════════════════════"
            echo "  PIPELINE ABORTED — ILLEGAL PATTERNS DETECTED"
            echo "  See ILLEGAL_CODE_PURGE_PLAN.md for remediation steps"
            echo "════════════════════════════════════════════════════════"
            exit 1
          fi

          echo "✅ All checks passed — no illegal patterns detected"

      - name: Record scan result in Prometheus
        if: always()
        run: |
          # Incrementar contador para dashboard Legal Compliance
          RESULT=${{ job.status == 'success' && '0' || '1' }}
          curl -s -X POST http://localhost:9091/metrics/job/ci_illegal_scan \
            --data-binary "cardex_ci_illegal_pattern_violations_total $RESULT" || true

  # ═══════════════════════════════════════════════════════
  # STEP 3 — Unit Tests Go
  # ═══════════════════════════════════════════════════════
  unit-tests:
    name: Unit Tests
    needs: [lint, illegal-pattern-scan]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Go
        uses: actions/setup-go@v5
        with:
          go-version: ${{ env.GO_VERSION }}
          cache: true

      - name: Run unit tests with coverage
        run: |
          go test -v -race -coverprofile=coverage.out -covermode=atomic \
            -timeout=300s ./...

      - name: Check coverage thresholds
        run: |
          # Packages críticos requieren mínimo 70% coverage
          CRITICAL_PACKAGES=(
            "cardex/internal/quality"
            "cardex/internal/extraction"
            "cardex/pkg/vin"
            "cardex/pkg/equipment"
            "cardex/internal/graph"
          )

          FAILED=0
          for pkg in "${CRITICAL_PACKAGES[@]}"; do
            COV=$(go tool cover -func=coverage.out | grep "$pkg" | \
                  awk '{sum+=$3; count++} END {if(count>0) print sum/count; else print 0}' | \
                  tr -d '%')
            if (( $(echo "$COV < 70.0" | bc -l) )); then
              echo "❌ Coverage too low for $pkg: ${COV}% (minimum: 70%)"
              FAILED=$((FAILED + 1))
            else
              echo "✅ $pkg: ${COV}%"
            fi
          done

          if [ "$FAILED" -gt 0 ]; then
            echo "Coverage gate failed for $FAILED package(s)"
            exit 1
          fi

      - name: Upload coverage report
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: coverage.out

  # ═══════════════════════════════════════════════════════
  # STEP 4 — Integration Tests
  # ═══════════════════════════════════════════════════════
  integration-tests:
    name: Integration Tests
    needs: [unit-tests]
    runs-on: ubuntu-latest
    services:
      # SQLite no requiere servicio externo
    steps:
      - uses: actions/checkout@v4

      - name: Setup Go
        uses: actions/setup-go@v5
        with:
          go-version: ${{ env.GO_VERSION }}
          cache: true

      - name: Download test fixtures (NHTSA sample, VIN dataset)
        run: |
          # Dataset de integración: 1000 VINs reales + 500 vehicles con escenarios de validación
          # Almacenado en el repo en testdata/ (no contiene datos personales)
          ls testdata/
          test -f testdata/vin_sample_1000.csv || exit 1
          test -f testdata/vehicle_sample_500.json || exit 1
          test -f testdata/nhtsa_sample.db || exit 1

      - name: Run integration tests
        run: |
          go test -v -tags=integration -timeout=600s \
            ./tests/integration/...
        env:
          NHTSA_DB: testdata/nhtsa_sample.db
          FX_DB: testdata/fx_test.db
          NATS_EMBEDDED: true

      - name: Quality pipeline integration test
        run: |
          # Test del pipeline V01-V20 completo sobre dataset de muestra
          go test -v -tags=integration -run TestQualityPipelineEndToEnd \
            -timeout=300s ./tests/integration/quality/...

  # ═══════════════════════════════════════════════════════
  # STEP 5 — Build Binaries
  # ═══════════════════════════════════════════════════════
  build:
    name: Build Binaries
    needs: [integration-tests]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Go
        uses: actions/setup-go@v5
        with:
          go-version: ${{ env.GO_VERSION }}
          cache: true

      - name: Build all service binaries
        run: |
          mkdir -p dist/

          SERVICES=(discovery extraction quality nlg index api sse)
          for svc in "${SERVICES[@]}"; do
            echo "Building cardex-$svc..."
            CGO_ENABLED=1 GOOS=linux GOARCH=amd64 \
              go build -o "dist/cardex-$svc" \
              -ldflags="-s -w -X main.Version=$(git describe --tags --always) \
                        -X main.BuildDate=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
              "./cmd/$svc/"
            echo "  Size: $(du -sh dist/cardex-$svc | cut -f1)"
          done

          # Build fx-updater tool
          CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
            go build -o dist/cardex-fx-updater ./cmd/fx-updater/

          ls -lh dist/

      - name: Verify binary integrity (not stripped of version info)
        run: |
          for bin in dist/cardex-*; do
            version=$(./dist/cardex-api --version 2>/dev/null | head -1 || echo "unknown")
            echo "$bin: $version"
          done

      - name: Upload build artifacts
        uses: actions/upload-artifact@v4
        with:
          name: cardex-binaries-${{ github.sha }}
          path: dist/
          retention-days: 7

  # ═══════════════════════════════════════════════════════
  # STEP 6 — Deploy (solo en push a main, ventana horaria)
  # ═══════════════════════════════════════════════════════
  deploy:
    name: Deploy to VPS
    needs: [build]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    environment: production
    steps:
      - uses: actions/checkout@v4

      - name: Check deploy window (03:00-05:00 CET)
        run: |
          HOUR=$(TZ=Europe/Madrid date +%H)
          DAY=$(TZ=Europe/Madrid date +%u)  # 1=Monday, 7=Sunday

          # Bloquear deploys en fin de semana (opcional, quitar si se necesita)
          # if [ "$DAY" -ge 6 ]; then
          #   echo "⏰ Deploy blocked: weekend"
          #   exit 1
          # fi

          if [ "$HOUR" -lt 3 ] || [ "$HOUR" -ge 5 ]; then
            echo "⏰ Outside deploy window (03:00-05:00 CET). Current hour: ${HOUR}:00 CET"
            echo "   Deploy will be triggered manually or at next window."
            echo "   Hint: Use workflow_dispatch to force a deploy outside window."
            exit 1
          fi
          echo "✅ Inside deploy window: ${HOUR}:00 CET"

      - name: Download build artifacts
        uses: actions/download-artifact@v4
        with:
          name: cardex-binaries-${{ github.sha }}
          path: dist/

      - name: Setup SSH
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.VPS_SSH_KEY }}" > ~/.ssh/cardex_deploy
          chmod 600 ~/.ssh/cardex_deploy
          echo "StrictHostKeyChecking no" >> ~/.ssh/config

      - name: Determine changed services
        id: changed
        run: |
          # Solo reiniciar servicios cuyos fuentes cambiaron
          CHANGED=""
          git diff --name-only ${{ github.event.before }} ${{ github.sha }} | while read f; do
            case "$f" in
              cmd/discovery/*|internal/discovery/*) echo "discovery" >> /tmp/changed_svcs ;;
              cmd/extraction/*|internal/extraction/*) echo "extraction" >> /tmp/changed_svcs ;;
              cmd/quality/*|internal/quality/*) echo "quality" >> /tmp/changed_svcs ;;
              cmd/nlg/*|internal/nlg/*) echo "nlg" >> /tmp/changed_svcs ;;
              cmd/index/*|internal/index/*) echo "index" >> /tmp/changed_svcs ;;
              cmd/api/*|internal/api/*) echo "api" >> /tmp/changed_svcs ;;
              cmd/sse/*) echo "sse" >> /tmp/changed_svcs ;;
              internal/graph/*|pkg/*) echo "all" >> /tmp/changed_svcs ;;
            esac
          done
          CHANGED=$(sort -u /tmp/changed_svcs | tr '\n' ' ')
          echo "changed_services=$CHANGED" >> $GITHUB_OUTPUT
          echo "Changed services: $CHANGED"

      - name: Deploy binaries via rsync
        run: |
          CHANGED="${{ steps.changed.outputs.changed_services }}"
          VPS="${{ secrets.VPS_HOST }}"
          SSH_KEY="~/.ssh/cardex_deploy"

          if echo "$CHANGED" | grep -q "all"; then
            SERVICES=(discovery extraction quality nlg index api sse)
          else
            SERVICES=($CHANGED)
          fi

          for svc in "${SERVICES[@]}"; do
            if [ -f "dist/cardex-$svc" ]; then
              echo "Deploying cardex-$svc..."
              rsync -az -e "ssh -i $SSH_KEY" \
                "dist/cardex-$svc" \
                "cardex@$VPS:/tmp/cardex-$svc.new"
            fi
          done

          # Atomic replacement + restart (en el VPS)
          ssh -i "$SSH_KEY" "cardex@$VPS" bash << 'REMOTE'
            set -euo pipefail
            for f in /tmp/cardex-*.new; do
              svc=$(basename $f .new)
              echo "Installing $svc..."
              sudo install -o root -g root -m 755 "$f" "/usr/local/bin/$svc"
              rm -f "$f"
              # Solo reiniciar si el servicio no es el NLG batch timer (se gestiona diferente)
              if [ "$svc" != "cardex-nlg" ]; then
                sudo systemctl restart "${svc}.service"
                sleep 2
                sudo systemctl is-active --quiet "${svc}.service" && \
                  echo "✅ $svc restarted OK" || \
                  (echo "❌ $svc failed to restart"; sudo journalctl -u "${svc}" -n 20; exit 1)
              fi
            done
          REMOTE

      - name: Deploy static assets (Manual Review UI)
        run: |
          if git diff --name-only ${{ github.event.before }} ${{ github.sha }} | grep -q "^frontend/"; then
            echo "Building and deploying frontend..."
            cd frontend
            npm ci
            npm run build
            rsync -az -e "ssh -i ~/.ssh/cardex_deploy" \
              dist/ "cardex@${{ secrets.VPS_HOST }}:/srv/cardex/www/"
          fi

  # ═══════════════════════════════════════════════════════
  # STEP 7 — Smoke Test post-deploy
  # ═══════════════════════════════════════════════════════
  smoke-test:
    name: Smoke Test
    needs: [deploy]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    steps:
      - name: Wait for services to stabilize
        run: sleep 15

      - name: Health endpoint check
        run: |
          RESPONSE=$(curl -sf --max-time 10 \
            "https://${{ secrets.CARDEX_DOMAIN }}/health" || echo "FAIL")

          if [ "$RESPONSE" = "FAIL" ]; then
            echo "❌ Health endpoint not responding"
            exit 1
          fi

          STATUS=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))")
          if [ "$STATUS" != "ok" ]; then
            echo "❌ Health status not OK: $RESPONSE"
            exit 1
          fi
          echo "✅ Health endpoint: $STATUS"

      - name: API smoke test (vehicles search)
        run: |
          RESPONSE=$(curl -sf --max-time 15 \
            -H "X-API-Key: ${{ secrets.SMOKE_TEST_API_KEY }}" \
            "https://${{ secrets.CARDEX_DOMAIN }}/api/vehicles?make=BMW&per_page=1" \
            || echo "FAIL")

          if [ "$RESPONSE" = "FAIL" ]; then
            echo "❌ Vehicle search API not responding"
            exit 1
          fi

          TOTAL=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',0))")
          if [ "$TOTAL" -lt 1 ]; then
            echo "⚠️  Warning: 0 vehicles returned from search — index may be empty"
          else
            echo "✅ API smoke test: $TOTAL vehicles indexed"
          fi

      - name: SSE endpoint check
        run: |
          # Verificar que el endpoint SSE responde con headers correctos
          HEADERS=$(curl -sf --max-time 5 -I \
            "https://${{ secrets.CARDEX_DOMAIN }}/events" \
            -H "Accept: text/event-stream" || echo "FAIL")

          if echo "$HEADERS" | grep -qi "text/event-stream"; then
            echo "✅ SSE endpoint: content-type OK"
          else
            echo "⚠️  SSE endpoint header unexpected: $HEADERS"
          fi

      - name: Alert on failure
        if: failure()
        run: |
          curl -X POST "${{ secrets.ALERT_WEBHOOK }}" \
            -H "Content-Type: application/json" \
            -d "{\"text\":\"🚨 CARDEX deploy smoke test FAILED — commit ${{ github.sha }}\"}"
```

---

## Configuración de golangci-lint (`.golangci.yml`)

```yaml
run:
  timeout: 5m
  go: '1.22'

linters:
  enable:
    - errcheck        # verificar manejo de errores
    - gosimple        # simplificaciones
    - govet           # análisis estático go vet
    - ineffassign     # asignaciones sin efecto
    - staticcheck     # análisis estático avanzado
    - unused          # código sin usar
    - gofmt           # formato
    - goimports       # imports ordenados
    - misspell        # errores ortográficos en comentarios
    - gosec           # análisis de seguridad

linters-settings:
  gosec:
    excludes:
      - G304  # file path from variable (controlado en nuestro caso)

issues:
  exclude-rules:
    - path: _test.go
      linters: [gosec, errcheck]
```

---

## Deploy manual (fuera de ventana horaria)

Para deploys urgentes (hotfix) fuera de la ventana 03:00-05:00:

```bash
# Desde el VPS via SSH
ssh cardex@vps

# Build local del hotfix en el VPS (si Go está instalado)
cd /srv/cardex/src
git pull
go build -o /tmp/cardex-api.new ./cmd/api/
sudo install -o root -g root -m 755 /tmp/cardex-api.new /usr/local/bin/cardex-api
sudo systemctl restart cardex-api.service
sudo systemctl is-active cardex-api.service

# O bien: forzar via Forgejo workflow_dispatch desde el dashboard
```

---

## Rollback

```bash
# Los binarios anteriores se conservan por 7 días en los artifacts de Forgejo
# Rollback manual:

# 1. Descargar artifact del commit anterior desde Forgejo
# 2. rsync al VPS
# 3. systemctl restart

# Rollback de base de datos SQLite:
# Solo es necesario si el deploy modificó el schema
sqlite3 /srv/cardex/db/main.db ".restore /srv/cardex/backups/latest_pre_deploy.db"
```

---

## Branches y flujo de trabajo

```
main            → producción, protegida, requiere CI pass
  └── claude/*  → worktrees de agentes Claude (CI requerido, merge sin aprobación humana)
  └── feature/* → desarrollo manual (CI requerido, PR + aprobación)
  └── hotfix/*  → correcciones urgentes (CI requerido, deploy manual post-merge)
```

**Branch protection en main:**
- Require status checks: lint, illegal-pattern-scan, unit-tests, integration-tests, build
- Require branches to be up to date before merging
- No force push
- No delete
- Require linear history (squash merge recomendado)
