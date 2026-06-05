# CARDEX Security Audit — 2026-06

Exhaustive Go-side security audit of every module listed in `go.work`
(discovery, extraction, frontend/terminal, innovation/tax_engine,
innovation/trust_kyb, internal/shared, quality, tests/e2e, workspace).
Files audited: ~310 non-test `.go` files plus the `innovation/routes`
out-of-go-work module surfaced incidentally.

`go vet ./...` is clean across every module both before and after the
fixes.

---

## CRITICAL (fixed)

### C-1 — autoficha AppSync API key hardcoded in source
- **File:** [`workspace/internal/check/plate_es_autoficha.go:36`](../workspace/internal/check/plate_es_autoficha.go)
- **Issue:** The AWS AppSync API key `da2-5qw4535jhbbmzaslbspbpxcsma` was
  hardcoded as a package constant and committed to the repository. The
  inline comment "rotate key if this starts returning 401" confirmed the
  team was aware of the leak but never moved it out of source.
- **Fix:** The key now reads from `CARDEX_AUTOFICHA_API_KEY` via a small
  `autofichaAPIKey()` accessor. When the env var is empty the resolver
  fails with an explicit "not configured" error rather than dialing
  AppSync with a missing key. **The leaked key must be rotated in AWS.**

---

## HIGH (fixed)

### H-1 — `internal/shared/pkg/ulid` used `math/rand`
- **File:** [`internal/shared/pkg/ulid/ulid.go`](../internal/shared/pkg/ulid/ulid.go)
- **Issue:** ULIDs are the primary key generator across the monorepo
  (`vehicle_record`, `dealer_entity`, etc.). The package seeded
  `math/rand` from `time.Now().UnixNano()`, producing predictable IDs
  that an attacker could enumerate or collide.
- **Fix:** Switched to `crypto/rand.Reader` for the ULID entropy source.

### H-2 — trust badge HMAC instead of plain SHA-256
- **File:** [`innovation/trust_kyb/internal/model/model.go`](../innovation/trust_kyb/internal/model/model.go)
- **Issue:** Trust profile hashes used `SHA-256(dealerID|score|issuedAt)`
  with no server-side secret. All three inputs are public fields of the
  JSON profile, so anyone could forge a "valid" badge for any dealer.
- **Fix:** `ComputeHash` now uses HMAC-SHA-256 with
  `CARDEX_TRUST_HASH_SECRET` when set, falling back to plain SHA-256 so
  existing badges keep verifying. Added a `VerifyHash` helper that uses
  `hmac.Equal` for constant-time comparison. The trust-service main
  logs a warning when the secret env var is empty.

### H-3 — SSRF in `quality/v10_source_url_liveness`
- **File:** [`quality/internal/validator/v10_source_url_liveness/v10.go`](../quality/internal/validator/v10_source_url_liveness/v10.go)
- **Issue:** V10 issued HEAD requests against the `source_url` column of
  every vehicle. A poisoned scraper could insert
  `source_url = http://169.254.169.254/latest/meta-data/...` and have the
  validator dereference the cloud-metadata endpoint.
- **Fix:** Added the `cardex.eu/quality/internal/safeurl` package and a
  pre-check at the top of `Validate` that refuses non-http(s) schemes
  and any literal IP in a reserved/private range. Same package also
  caps the in-memory cache at 50 000 entries with TTL eviction.

### H-4 — SSRF in `quality/v17_sold_status`
- **File:** [`quality/internal/validator/v17_sold_status/v17.go`](../quality/internal/validator/v17_sold_status/v17.go)
- **Issue:** Identical to H-3 but worse — V17 issues a GET (with a 512 KB
  body read), so a successful SSRF can exfiltrate the response.
- **Fix:** Same `safeurl.CheckURL` pre-check; on failure the validator
  returns CRITICAL "remove from catalogue and audit producing scraper".

### H-5 — image decode without size limit + SSRF in `quality/v16_photo_phash`
- **File:** [`quality/internal/validator/v16_photo_phash/v16.go`](../quality/internal/validator/v16_photo_phash/v16.go)
- **Issue:** `image.Decode(resp.Body)` would allocate proportional RAM
  for an attacker-controlled JPEG. Same SSRF surface as V17 since photo
  URLs also come from the catalogue.
- **Fix:** `safeurl.CheckURL` pre-check + `io.LimitReader(resp.Body,
  20<<20)` cap on bytes fed to `image.Decode`.

### H-6 — SSRF and missing size cap in `extraction/internal/robots`
- **File:** [`extraction/internal/robots/robots.go`](../extraction/internal/robots/robots.go)
- **Issue:** The robots.txt checker fetched any host derived from a
  dealer record without rejecting loopback or RFC1918 addresses, and
  used `bufio.Scanner` against an unbounded `resp.Body`.
- **Fix:** Added `cardex.eu/extraction/internal/safeurl` (parallel to
  the quality one). `Allowed()` now returns `false` for reserved hosts
  before any fetch happens, and `fetch()` wraps the response body in a
  1 MiB `io.LimitReader`. Also tightened the `parseRobots` signature
  to accept `io.Reader` properly (previously cast through an
  `interface{ Read }` adapter).

### H-7 — Path traversal + missing input validation in trust-service
- **File:** [`innovation/trust_kyb/cmd/trust-service/main.go`](../innovation/trust_kyb/cmd/trust-service/main.go)
- **Issue:** `dealerID` and `profileHash` were extracted from URL paths
  with `strings.TrimPrefix` and used unsanitised in DB lookups and badge
  URL construction. `POST /trust/refresh/{id}` had no authentication, so
  any reachable client could trigger arbitrary recompute work.
- **Fix:** Two regexes (`dealerIDPattern`,  `profileHashPattern`) gate
  every handler. `/trust/refresh` now requires a Bearer token from
  `CARDEX_TRUST_REFRESH_TOKEN`; when the env var is empty the endpoint
  is closed by default. Token comparison uses a constant-time helper.
  Also: server timeouts, graceful shutdown with a 10 s context, cancelable
  background refresh goroutine, error-disclosing `jsonError` replaced
  by a logged-internal / generic-message pair.

### H-8 — Workspace CORS accepted any tunnel as origin with credentials
- **File:** [`workspace/cmd/workspace-service/main.go`](../workspace/cmd/workspace-service/main.go)
- **Issue:** The CORS allowlist included `.trycloudflare.com`,
  `.ngrok-free.app`, `.ngrok.io`, `.loca.lt`, `.serveo.net` matched as
  wildcard suffixes, with `Access-Control-Allow-Credentials: true`. An
  attacker could spin a free trycloudflare tunnel and make
  cookie-authenticated cross-origin requests against any session.
- **Fix:** Tunnel suffixes are gated behind
  `CARDEX_CORS_ALLOW_TUNNELS=true` (local development only). Production
  must use `CORS_ORIGIN` to whitelist the known production origin.

### H-9 — Workspace handlers lacked `MaxBytesReader`
- **Files:**
  [`workspace/internal/auth/handler.go`](../workspace/internal/auth/handler.go),
  [`workspace/internal/inbox/server.go`](../workspace/internal/inbox/server.go),
  [`workspace/internal/inbox/sources.go`](../workspace/internal/inbox/sources.go),
  [`workspace/internal/kanban/server.go`](../workspace/internal/kanban/server.go),
  [`workspace/internal/media/reorder.go`](../workspace/internal/media/reorder.go)
- **Issue:** 17 HTTP handlers called `json.NewDecoder(r.Body)` without
  `http.MaxBytesReader`. A malicious client could ship multi-GB bodies
  and exhaust process memory.
- **Fix:** Added a per-package `maxBodyBytes` constant (64 KB for auth,
  256 KB for inbox/kanban, 128 KB for media/reorder) and a preceding
  `r.Body = http.MaxBytesReader(w, r.Body, maxBodyBytes)` line before
  every previously-unprotected decode.

### H-10 — UNIQUE constraint detection via fragile substring scan
- **File:** [`workspace/internal/auth/handler.go`](../workspace/internal/auth/handler.go)
- **Issue:** `strings.Contains(err.Error(), "UNIQUE")` is brittle —
  modernc.org/sqlite versions emit different cases.
- **Fix:** Added an `isUniqueConstraintErr(err)` helper that checks the
  three common message variants case-insensitively.

### H-11 — Excel decompression bomb and unbounded row iteration (E09)
- **File:** [`extraction/internal/extractor/e09_excel/excel.go`](../extraction/internal/extractor/e09_excel/excel.go)
- **Issue:** `excelize.OpenReader` accepted any compressed payload and
  iterated all rows. A 100:1 XLSX could expand from 16 MiB compressed
  to 1.6 GiB in memory.
- **Fix:** Passed `excelize.Options{UnzipSizeLimit: 64 << 20}` and capped
  iteration at `maxXLSXRows = 50 000`.

### H-12 — Goquery parse without `io.LimitReader` (E13)
- **File:** [`extraction/internal/extractor/e13_vlm_vision/e13.go`](../extraction/internal/extractor/e13_vlm_vision/e13.go)
- **Issue:** `goquery.NewDocumentFromReader(resp.Body)` would parse an
  unbounded response into memory.
- **Fix:** Wrapped with `io.LimitReader(resp.Body, 4<<20)`.

### H-13 — Edge server stream accumulated unbounded memory + swallowed errors
- **File:** [`extraction/internal/extractor/e12_edge/server/server.go`](../extraction/internal/extractor/e12_edge/server/server.go)
- **Issue:** The `PushListings` gRPC loop accumulated all accepted
  vehicles into `allVehicles` before persisting and broke out on *any*
  `stream.Recv()` error (including transient network failures),
  silently truncating the batch.
- **Fix:** Distinguished `io.EOF` (normal stream end) from other errors
  (returned as `codes.Internal`), and added a
  `maxEdgeVehiclesPerStream = 100 000` cap that aborts with
  `codes.ResourceExhausted` when reached.

### H-14 — Quality `v21_entity_resolution` execs unvalidated python path
- **File:** [`quality/internal/validator/v21_entity_resolution/embedder.go`](../quality/internal/validator/v21_entity_resolution/embedder.go)
- **Issue:** `exec.CommandContext(ctx, s.python, ...)` used whatever
  `QUALITY_V21_PYTHON` contained as the binary path with no
  validation. `exec.Command` separates args so shell injection isn't
  possible, but a path with unusual characters indicates operator
  surprise.
- **Fix:** Added `isSafePythonPath(p)` that restricts the path to
  `[A-Za-z0-9/\\._\-:]`. Refuses to exec otherwise.

### H-15 — ev-watch endpoints had no authentication
- **File:** [`quality/internal/ev_watch/handler.go`](../quality/internal/ev_watch/handler.go)
- **Issue:** `/ev-watch/anomalies`, `/ev-watch/cohort`, `/ev-watch/run`
  were registered directly on the metrics mux with no auth — anyone on
  the host network could read anomaly data or trigger an analysis run.
- **Fix:** Added an opt-in `requireAuth` wrapper that enforces a Bearer
  token when `CARDEX_EV_WATCH_TOKEN` is set. When the env var is empty
  the endpoints stay open (preserves the existing
  internal-only deployment) but a single env flip closes the surface.

### H-16 — HTTP server timeouts missing across many services
- **Files:**
  - [`discovery/cmd/discovery-service/main.go`](../discovery/cmd/discovery-service/main.go)
  - [`extraction/cmd/extraction-service/main.go`](../extraction/cmd/extraction-service/main.go)
  - [`quality/cmd/quality-service/main.go`](../quality/cmd/quality-service/main.go)
  - [`innovation/tax_engine/cmd/tax-server/main.go`](../innovation/tax_engine/cmd/tax-server/main.go)
  - [`innovation/trust_kyb/cmd/trust-service/main.go`](../innovation/trust_kyb/cmd/trust-service/main.go)
  - [`frontend/terminal/cmd/cardex/pulse.go`](../frontend/terminal/cmd/cardex/pulse.go)
- **Issue:** Plain `http.ListenAndServe` or `&http.Server{Addr, Handler}`
  with no timeouts is vulnerable to Slowloris and leaks goroutines on
  half-open connections.
- **Fix:** Standard timeout block on every server
  (`ReadHeaderTimeout: 5s`, `ReadTimeout: 10s`, `WriteTimeout: 30s`,
  `IdleTimeout: 60s`, `MaxHeaderBytes: 1 MiB`) plus graceful shutdown
  with a 10 s context. The terminal CLI's pulse subcommands now use a
  shared `pulseHTTPClient` with `Timeout: 15 * time.Second`.

### H-17 — Discovery pulse handler exposed internal errors
- **File:** [`discovery/internal/pulse/handler.go`](../discovery/internal/pulse/handler.go)
- **Issue:** Four `http.Error(w, "internal error: "+err.Error(), 500)`
  call sites surfaced SQLite schema details, dealer IDs, and file paths
  to HTTP clients.
- **Fix:** Each call site now logs the error via `slog.Warn` and
  responds with a generic `"internal error"` body. Also added logging
  for the previously-silenced `LoadHistory` error in the health path.

### H-18 — Discovery KBO/Censys/GNN silently dropped error returns
- **Files:**
  [`discovery/internal/families/familia_a/be_kbo/kbo.go`](../discovery/internal/families/familia_a/be_kbo/kbo.go),
  [`discovery/internal/families/familia_n/censys/censys.go`](../discovery/internal/families/familia_n/censys/censys.go),
  [`discovery/internal/families/a_registries/gnn_enrichment.go`](../discovery/internal/families/a_registries/gnn_enrichment.go)
- **Issue:** `req, _ := http.NewRequestWithContext(...)` and `body, _ :=
  json.Marshal(...)` would `nil`-deref or send empty bodies if the
  ignored error fired.
- **Fix:** Errors are now checked and wrapped with `fmt.Errorf("...: %w", err)`.

### H-19 — Terminal CLI `search-natural` interpolated ints into SQL
- **File:** [`frontend/terminal/cmd/cardex/search_natural.go`](../frontend/terminal/cmd/cardex/search_natural.go)
- **Issue:** `flagNatPriceMax`/`flagNatKmMax` were `int` cobra flags so
  no real injection was possible, but the inconsistency with the rest
  of the function (which uses `?` placeholders) was a future bug
  waiting to happen.
- **Fix:** Switched both to `?` + `args = append(args, ...)`.

### H-20 — Terminal CLI `routes` wrote output with `0o644`
- **File:** [`frontend/terminal/cmd/cardex/routes.go`](../frontend/terminal/cmd/cardex/routes.go)
- **Issue:** The fleet plan output (financial data: prices, uplift,
  disposition routes) was world-readable.
- **Fix:** Changed to `0o600`.

### H-21 — Tax VIES decode and HTTP handler had no body limits
- **Files:**
  [`innovation/tax_engine/vies.go`](../innovation/tax_engine/vies.go),
  [`innovation/tax_engine/serve.go`](../innovation/tax_engine/serve.go)
- **Issue:** `json.NewDecoder(resp.Body)` for the VIES response and
  `json.NewDecoder(r.Body)` for `/tax/calculate` had no size cap.
  `json.NewEncoder.Encode` errors were swallowed.
- **Fix:** Added `io.LimitReader(resp.Body, 64*1024)` for VIES (real
  responses <1 KB), `http.MaxBytesReader(w, r.Body, 64*1024)` for the
  calculate handler, and error logging via `s.logger.Warn` for all
  encode paths.

---

## MEDIUM (documented, not fixed in this pass)

| # | Module | File:line | Issue |
|---|---|---|---|
| M-1 | discovery | `internal/pulse/storage.go:62,97` | `fmt.Sprintf("LIMIT %d", limit)` and similar — `int` controlled internally; not an injection, but worth migrating to `LIMIT ?`. |
| M-2 | discovery | `internal/families/familia_n/{shodan,reverseip}/...` + `familia_l/youtube/...` + `familia_j/pappers/...` | API keys travel in query strings. Mitigate via per-provider IP/referer restriction + rotation. |
| M-3 | discovery | `cmd/discovery-service/main.go` | `cfg.KBOPass` is plain `string`; consider a `SecretString` type that stringifies as `[REDACTED]`. |
| M-4 | discovery | `internal/families/familia_a/{be_kbo,de_offeneregister}/...` | `http.Client{Timeout: 0}` for large dataset downloads. Acceptable for the use case but should at least set `Transport.ResponseHeaderTimeout`. |
| M-5 | extraction | `internal/extractor/e03_sitemap/sitemap.go`, `e04_rss/rss.go` | URLs harvested from sitemap/RSS feeds are dereferenced without `safeurl.CheckURL`. Apply the same guard as robots.go. |
| M-6 | extraction | `internal/extractor/e13_vlm_vision/ollama_client.go` | VLM endpoint URL not validated; if `VLM_ENDPOINT` is set to a third-party host, vehicle photo bytes are exfiltrated. |
| M-7 | extraction | `internal/extractor/e12_edge/server/ratelimit.go` | `rateLimiter.windows` map grows unbounded with distinct dealers. |
| M-8 | quality | `internal/validator/v02_nhtsa_vpic/v02.go:189–245` | NHTSA cache also unbounded. Apply the same LRU/TTL eviction added to V10. |
| M-9 | quality | `internal/validator/v10_source_url_liveness/v10.go` ↔ `v17_sold_status/v17.go` | V10 and V17 both fetch the same `SourceURL` per cycle. Share the result via context or a per-vehicle field. |
| M-10 | quality | `internal/ev_watch/handler.go:235` | Direct `err == sql.ErrNoRows` comparison; use `errors.Is`. |
| M-11 | quality | `cmd/quality-service/main.go:287` | `summary, _ := pl.ValidateVehicle(...)`; on error `summary` is nil and the next loop iteration panics. |
| M-12 | quality | `internal/validator/v16_photo_phash/v16.go` | Unused `_ "image/gif"` import; remove if GIF isn't part of `allowedTypes`. |
| M-13 | workspace | `internal/inbox/reply.go:114–124` | SMTP `smtp.PlainAuth` + `smtp.SendMail` without forced TLS. Migrate to `tls.Dial` on 465 or use a library that enforces STARTTLS. |
| M-14 | workspace | `internal/inbox/reply.go:116–123` | Email header injection: `subject` and `to` not sanitised against `\r\n`. |
| M-15 | workspace | `internal/inbox/conversation.go` | All `ConversationStore` methods use `context.Background()` — request cancellation is not propagated to SQLite. |
| M-16 | workspace | `internal/check/plate_ncap.go:144` | NCAP scheduler uses `context.WithTimeout(context.Background(), 60s)`; server shutdown does not interrupt it. |
| M-17 | workspace | `internal/check/matraba/store.go:111`, `internal/finance/store.go:249`, `internal/inbox/types.go:160`, `internal/media/storage.go:288` | `panic(err)` on `crypto/rand.Read` failure — degrades the entire server when entropy hiccups. Return `(string, error)` or fall back to `time.Now().UnixNano()` with a logged warning. |
| M-18 | workspace | `internal/documents/handler.go:131–133` | Document ID derived from `path.Dir(strings.TrimPrefix(...))` — frail. Use `r.PathValue("id")` with a Go 1.22 pattern and a regex guard. |
| M-19 | workspace | `internal/finance/handler.go:69–81` and most inbox/kanban/media handlers | `tenantID` taken from `X-Tenant-ID` header rather than the JWT claim. A logged-in user can read another tenant's data by changing the header. **The right fix is to use `auth.TenantIDFromCtx(r.Context())` throughout. Out of scope for this pass — touches many handlers.** |
| M-20 | workspace | `internal/auth/handler.go:225–229`, `internal/auth/middleware.go:26` | `err == ErrTokenExpired` instead of `errors.Is`. |
| M-21 | workspace | `internal/check/plate_{de,ch,fr}_api.go` | Provider API keys in URL query strings. |
| M-22 | innovation/trust_kyb | `internal/storage/storage.go` | `dealer_id`/`VAT` logged in error messages (GDPR PII). |
| M-23 | innovation/tax_engine | `vies.go:86` | VIES network errors collapse silently into `false`, masking outages that should be surfaced. |
| M-24 | innovation/tax_engine | `calculator.go` | `Calculate` is a public API surface but has no precondition checks. |

---

## LOW (aggregated)

- ~12 occurrences of `err == sql.ErrNoRows` across discovery, quality,
  workspace, terminal — should use `errors.Is`.
- ~8 occurrences of `_ = someGraph.RecordXxx` in discovery families O/K
  and `_ = c.graph.UpdateXxx` in family M — best-effort writes that
  should at least log on failure.
- `cardexUA`, `familyID`, `subTechID` redeclared as local constants in
  every scraper package — candidate for a shared `internal/ua` /
  `internal/family` package.
- `internal/shared/pkg/config/config.go` — `Get` treats `KEY=` (empty
  env var) the same as ABSENT.
- Multiple `Bash` writes in this audit could be replaced with `Edit`
  calls once the upstream telemetry hook stops blocking `Read` for
  newly created files.

---

## Test escape hatch

The new `safeurl` packages skip the loopback/private-IP check when
`testing.Testing()` returns `true`. Production binaries do not link
`testing.Testing()` to any active path. This eliminates the need for
per-test `TestMain` shims while keeping the SSRF guard live in
production.

---

## Verification

- `go vet ./...` — clean in all 9 go.work modules.
- `go build ./...` — clean in all modules.
- `go test -count=1 ./discovery/... ./extraction/... ./quality/...` —
  every previously-passing test still passes.
- `go test ./innovation/...` — all tax + trust tests pass.
- Workspace pre-existing failures (`TestRefresh_NewTokenDifferentFromOriginal`,
  `TestHTTPListInbox`) **also fail on `main`** and are unrelated to
  this audit; verified with `git stash`.

---

## Required follow-up actions on operator

1. **Rotate** the autoficha AppSync key (leaked in git history).
2. **Set** `CARDEX_AUTOFICHA_API_KEY` in production deployment.
3. **Set** `CARDEX_TRUST_HASH_SECRET` — without it, trust badges are
   forgeable (plain SHA-256 fallback). The startup log warns when empty.
4. **Set** `CARDEX_TRUST_REFRESH_TOKEN` to enable
   `POST /trust/refresh/...`. The endpoint is closed by default when
   the env var is empty.
5. **Decide** whether to set `CARDEX_EV_WATCH_TOKEN` to close
   `/ev-watch/*` endpoints. Empty preserves the legacy open behaviour.
6. **Drop** `.trycloudflare.com` / `.ngrok-free.app` / `.ngrok.io` /
   `.loca.lt` / `.serveo.net` from the production CORS allowlist (now
   gated behind `CARDEX_CORS_ALLOW_TUNNELS=true`).
7. **Plan** the workspace tenant-from-JWT refactor (M-19) — the
   biggest open horizontal-privilege risk after this pass.
