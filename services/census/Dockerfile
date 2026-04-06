# Multi-stage Go build for census service
FROM golang:1.24-alpine AS builder

RUN apk add --no-cache git gcc musl-dev

WORKDIR /build

COPY internal/shared ./internal/shared
COPY services/census ./services/census

WORKDIR /build/services/census

ENV GOWORK=off
RUN go build -ldflags="-s -w" -o /app/server ./cmd/census/...

# ── Runner ────────────────────────────────────────────────────────────────────
FROM alpine:3.20 AS runner
RUN apk add --no-cache ca-certificates tzdata
WORKDIR /app
COPY --from=builder /app/server ./server
USER nobody
CMD ["./server"]
