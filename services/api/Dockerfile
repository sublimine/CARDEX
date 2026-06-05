# CARDEX Cross-Border Price Intelligence API — multi-stage build.
# Build context is the repo root (see docker-compose.yml `api` service).
# syntax=docker/dockerfile:1

# ── Stage 1: build ───────────────────────────────────────────────────────────
FROM golang:1.26.2-bookworm AS builder

# Independently deployable module: never rely on workspace resolution.
ENV CGO_ENABLED=0 GOOS=linux GOWORK=off

WORKDIR /src/services/api

# Cache deps independently of source changes.
COPY services/api/go.mod services/api/go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download

COPY services/api/ ./

RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    go build -ldflags="-s -w" -trimpath -o /out/cardex-api ./cmd/api-service/

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
# Alpine (not distroless) so the compose healthcheck's wget probe is available.
FROM alpine:3.21

RUN apk add --no-cache ca-certificates wget && adduser -D -u 65532 cardex

USER 65532:65532

COPY --from=builder /out/cardex-api /usr/local/bin/cardex-api

EXPOSE 8080
ENV PORT=8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget -q -O /dev/null http://localhost:8080/healthz || exit 1

ENTRYPOINT ["/usr/local/bin/cardex-api"]
