// Standalone health-probe module for CARDEX distroless images.
// Built in the Dockerfile builder stage and copied into the final
// distroless/static image, which has no shell, wget or curl.
// Pure standard library — no external dependencies, builds offline.
module cardex/healthcheck

go 1.26
