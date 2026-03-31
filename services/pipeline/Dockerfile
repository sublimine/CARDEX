# Multi-stage Go build for pipeline service (pipeline worker + meili-sync)
FROM golang:1.23-alpine AS builder

RUN apk add --no-cache git gcc musl-dev

WORKDIR /build

# Copy go.work and workspace modules
COPY go.work* ./
COPY internal/shared ./internal/shared
COPY services/pipeline ./services/pipeline

WORKDIR /build/services/pipeline

ARG CMD=pipeline
RUN go build -ldflags="-s -w" -o /app/server ./cmd/${CMD}/...

# ── Runner ────────────────────────────────────────────────────────────────────
FROM alpine:3.20 AS runner
RUN apk add --no-cache ca-certificates tzdata
WORKDIR /app
COPY --from=builder /app/server ./server
USER nobody
CMD ["./server"]
