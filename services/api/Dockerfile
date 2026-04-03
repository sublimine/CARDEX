# Multi-stage Go build for api service
FROM golang:1.23-alpine AS builder

RUN apk add --no-cache git gcc musl-dev

WORKDIR /build

# Copy workspace and all required modules
COPY go.work* ./
COPY internal/shared ./internal/shared
COPY services/alpha  ./services/alpha
COPY services/api    ./services/api

WORKDIR /build/services/api

RUN go build -ldflags="-s -w" -o /app/server ./cmd/api/...

# ── Runner ────────────────────────────────────────────────────────────────────
FROM alpine:3.20 AS runner
RUN apk add --no-cache ca-certificates tzdata
WORKDIR /app
COPY --from=builder /app/server ./server
USER nobody
EXPOSE 8080
CMD ["./server"]
