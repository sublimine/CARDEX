# Multi-stage Go build for gateway service (HTTP + QUIC)
FROM golang:1.23-alpine AS builder

RUN apk add --no-cache git gcc musl-dev

WORKDIR /build

COPY go.work* ./
COPY services/gateway ./services/gateway

WORKDIR /build/services/gateway

RUN go build -ldflags="-s -w" -o /app/server ./cmd/gateway/...

# ── Runner ────────────────────────────────────────────────────────────────────
FROM alpine:3.20 AS runner
RUN apk add --no-cache ca-certificates tzdata
WORKDIR /app
COPY --from=builder /app/server ./server
USER nobody
EXPOSE 8080
EXPOSE 4433/udp
CMD ["./server"]
