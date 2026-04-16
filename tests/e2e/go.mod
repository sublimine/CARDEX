module cardex.eu/e2e

go 1.25.0

require (
	cardex.eu/discovery v0.0.0
	cardex.eu/extraction v0.0.0
	cardex.eu/quality v0.0.0
)

// Workspace replaces resolve these to local paths via go.work.
// The replace directives here serve as a fallback for builds outside
// the workspace (e.g., individual go mod tidy invocations).
replace (
	cardex.eu/discovery => ../../discovery
	cardex.eu/extraction => ../../extraction
	cardex.eu/quality => ../../quality
)
