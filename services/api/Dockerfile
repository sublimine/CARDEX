# Multi-stage Go build for api service
FROM golang:1.24-alpine AS builder

RUN apk add --no-cache git gcc musl-dev

WORKDIR /build

# Copy only the modules needed by the api service.
# GOWORK=off makes go use the replace directives in services/api/go.mod directly.
COPY internal/shared ./internal/shared
COPY services/alpha  ./services/alpha
COPY services/api    ./services/api

WORKDIR /build/services/api

ENV GOWORK=off
RUN go build -ldflags="-s -w" -o /app/server ./cmd/api/...

# ── Runner ────────────────────────────────────────────────────────────────────
FROM alpine:3.20 AS runner
RUN apk add --no-cache ca-certificates tzdata
WORKDIR /app
COPY --from=builder /app/server ./server
USER nobody
EXPOSE 8080
CMD ["./server"]
