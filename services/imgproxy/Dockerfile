FROM golang:1.24-alpine AS builder
RUN apk add --no-cache git
WORKDIR /build
COPY services/imgproxy ./services/imgproxy
WORKDIR /build/services/imgproxy
ENV GOWORK=off
RUN go build -ldflags="-s -w" -o /app/server ./cmd/imgproxy/...

FROM alpine:3.20 AS runner
RUN apk add --no-cache ca-certificates tzdata libwebp-tools
WORKDIR /app
COPY --from=builder /app/server ./server
USER nobody
CMD ["./server"]
