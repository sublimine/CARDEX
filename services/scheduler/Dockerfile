# Multi-stage Go build for scheduler service
FROM golang:1.24-alpine AS builder

RUN apk add --no-cache git gcc musl-dev

WORKDIR /build

COPY internal/shared ./internal/shared
COPY services/scheduler ./services/scheduler

WORKDIR /build/services/scheduler

ENV GOWORK=off
RUN go build -ldflags="-s -w" -o /app/server ./cmd/scheduler/...

# ── Runner ────────────────────────────────────────────────────────────────────
FROM alpine:3.20 AS runner
RUN apk add --no-cache ca-certificates tzdata
WORKDIR /app
COPY --from=builder /app/server ./server
USER nobody
CMD ["./server"]
