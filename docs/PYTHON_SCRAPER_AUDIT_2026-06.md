# Python Scraper Fleet — Security & Robustness Audit (2026-06)

**Scope:** every `.py` file under `scrapers/` (218 files, ~43,900 LOC — 182 production, 36 test).
**Date:** 2026-06-05 · **Method:** 5 parallel read-only analysis passes (engine / discovery / portals A–L / portals M–Z + mobile_re / common+pipeline+aggregators+intelligence+cli) followed by lead verification of every CRITICAL/HIGH site against the real source before any edit, then surgical fixes with a per-batch regression gate.
**Stack audited:** `curl_cffi` (TLS/JA3 impersonation), `camoufox`/Playwright, `httpx`, `aiohttp`, `asyncpg`, SQLite (WAL), MeiliSearch, `markitdown`.

> Authority: this audit follows `CONTEXT_FOR_AI.md` invariants — UA managed by `curl_cffi`/Camoufox (no literal override in the stealth fleet), JA3 coherence page 1..N per session, 0.3 req/s/domain default, robots.txt compliance, no secrets in git, SQLite integrity.

---

## 1. Executive summary

| Severity | Found | Fixed in this pass | Documented for owner decision |
|---|---|---|---|
| CRITICAL | 8 | 8 | 0 |
| HIGH | 28 | 21 | 7 |
| MEDIUM | ~60 | 12 | ~48 |
| LOW | ~80 | — | (noted inline / low value) |

**Regression gate (VERIFIED):** baseline `pytest scrapers/tests/` = **1 failed, 1308 passed** (the single failure is *pre-existing* — see §5). After all fixes: **1 failed, 1308 passed** — zero new regressions. Every changed module passes `py_compile` and an import smoke-test (35 files; the only non-importable module, `sitemap_bridge.py`, was already broken at HEAD — §5).

**The headline risks closed:** SQL injection into the crt.sh Postgres replica (external registry names), SSRF via dealer-controlled robots.txt / sitemap / `domain` (cloud-metadata + RFC1918 reachable, including a no-proxy direct-egress path in the tier classifier), decompression-bomb / unbounded document parsing of untrusted PDF/XLSX/DOCX, a Playwright driver-process leak, a whole-crawl-cycle crash on any transport error in 9 portals, and a non-finite-float crash in the normalization hot path.

---

## 2. Fixed in this pass (verified)

Each fix attacks the root cause, preserves success-path behavior byte-for-byte, and is covered by the regression gate. File references are post-fix.

### 2.1 CRITICAL

**SQLi-1 · SQL injection into crt.sh Postgres — `discovery/name_to_domain.py` `_resolve_one`**
Business `name` from external registries (SIRENE/Zefix/BMW) was concatenated into a `plainto_tsquery(...)` / `ILIKE` query with only hand-rolled `'`-escaping. **Root cause:** literal interpolation instead of bound parameters. **Fix:** asyncpg `$1`/`$2` bound parameters. Also closed the per-row crt.sh connection leak (`conn.close()` was on the happy path only → moved to `finally`).

**SQLi-2 · same injection pattern — `discovery/sources/ct_logs.py` `_query_crt_pg`**
Keyword/TLD currently static (latent, not yet exploitable) but identical anti-pattern. **Fix:** bound parameters; `LIMIT` interpolation hardened with `int()`.

**SSRF-1 · tier classifier, no-proxy direct egress — `engine/router/classifier.py` `classify`**
`domain` (freshly discovered, attacker-influenced) was fetched as `https://{host}/`, and the probe may run *without* a proxy → SSRF straight from the scraper host (metadata service, internal subnets). **Fix:** `is_safe_public_url(url, resolve=True)` guard (the only call site using DNS resolution, justified by the direct-egress blast radius) → returns the conservative `(T2, UNKNOWN, "ssrf-blocked")` spec on an unsafe target.

**SSRF-2 · sitemap/robots discovery — `pipeline/generic_extractor.py`**
robots.txt `Sitemap:` directives and `<sitemapindex>` children were queued and fetched with no host/scheme validation (listings were `_same_site`-filtered, but the sitemap URLs themselves were not). **Fix:** `is_safe_public_url(url)` on robots-declared sitemaps and on every sitemapindex child before queueing.

**DOC-1 · untrusted document parsing DoS — `common/doc_converter.py`**
`markitdown` was run on attacker-controlled PDF/XLSX/DOCX bytes with no size cap, no decompression-bomb guard, and no isolation. XLSX/DOCX are ZIP containers — a few-KB crafted zip expands to GB inside the converter. **Fix:** `_MAX_DOC_BYTES` (64 MiB) raw-input ceiling on `bytes_to_markdown`, `_MAX_HTML_CHARS` (8 Mi) on `html_to_markdown`, and `_is_zip_bomb()` rejecting ZIP payloads whose declared uncompressed total exceeds `_MAX_UNCOMPRESSED_BYTES` (512 MiB) or that are malformed. Removed a dead `except Exception: pass` masking a possible type error. **Residual (documented §3):** still runs in-thread without a hard kill-able timeout — process isolation + rlimit recommended.

**PW-1 · one bad page aborts the whole portal + driver leak — `common/pw_base.py`**
(a) `extract_fn`/`page.content()` ran *outside* the per-page try, so a single extraction error aborted the entire run; (b) `async_playwright().start()` (spawns the driver subprocess) sat *outside* the `try`, so a failing `chromium.launch()` leaked the driver; (c) the `response` interception handler swallowed errors with bare `pass`. **Fix:** navigation+extraction share one per-page guard (`break` on error, both Camoufox and Chromium paths); `start()` now inside a `try` with nested `finally` (`browser.close()` then `pw.stop()`); response handler logs at debug.

**LEAK-1 · `repair_pass.py` — pool + httpx + curl_cffi session, NO `finally`**
All three resources (`asyncpg.Pool`, `httpx.AsyncClient`, `curl_cffi.AsyncSession`) closed only on the normal path; any exception in the `while True` loop leaked all three. **Fix:** `try/finally` closing all three.

**LEAK-2 · `meili_enricher.py` / `meili_bridge.py` — clients created before the `try`**
Pool + httpx clients acquired before the protecting `try`, leaking on early failure. **Fix:** clients created inside the `try` (init-`None` + guarded close) / moved into the `finally` scope.

### 2.2 HIGH

**Portal transport-crash (9 files)** — `autoweek_nl`, `caravenue_com`, `classic_trader_com`, `coches_com`, `gocar_be`, `milanuncios_com`, `simplicicar_com`, `truckscout24_com`, `zoomcar_fr`: each called `session.get(...)` with no try/except, so any transport exception (DNS, reset, proxy drop, timeout) propagated out of `fetch_segment` → `run()` and **crashed the whole scrape cycle** (skipping trust accounting). The T2/T3 Cloudflare targets — where resets are *expected* — were the most exposed. **Fix:** wrap the GET in `try/except Exception → return []`, matching the ~40 sibling portals that already do. `caravenue_com` additionally got its inferred-JSON `.get()`-chain extraction guarded against `AttributeError`/`TypeError`/`KeyError`.

**SSRF-3 · DB/robots/sitemap URL fetches (4 discovery harvesters)** — `wp_rest_harvester.py` (DB `domain`), `sitemap_resolver.py` (robots-declared sitemaps + fallback host), `sitemap_bridge.py` (DB `sitemap_url`), `sitemap_image_harvester.py` (root sitemap + every child `<loc>`): all fetched untrusted URLs without validation. **Fix:** `is_safe_public_url(url)` guard at each fetch point, skipping unsafe targets with a log line.

**CRASH-1 · non-finite float — `pipeline/normalize.py` `parse_decimal` / `parse_int_loose`**
A NaN/±inf float from a permissive upstream JSON parser crashed `to_record` for the listing: `Decimal('NaN') >= 0` raises `InvalidOperation` (outside the existing `try`), `int(float('nan'))` raises `ValueError`, `int(float('inf'))` raises `OverflowError`, and `Decimal('Infinity')` would propagate as a poisoned price. **Fix:** `math.isfinite()` guard at the top of both numeric paths.

**LEAK-3 · resource leaks in discovery `run()` entrypoints (8 source/runner modules)** — `orphan_backfill.py`, `quality_gate.py`, and sources `fr_sirene_v311.py`, `osm_expanded_run.py`, `sirene_standalone.py`, `as24_curl_cffi.py`, `bovag.py`, `trustpilot.py`: `pool.close()` / session close ran outside any `try/finally`, leaking the pool (and curl_cffi session) on any exception. **Fix:** cleanup moved into `finally`.

**LOOP-1 · unbounded pagination — `mobile_re/client.py` `exhaust`**
`while True` paginated until a falsy `next_page_token`; a hostile/buggy API returning a perpetual or repeating token loops forever, accumulating URLs until OOM (the web base has a `MAX_PAGES` ceiling; this mobile base had none). **Fix:** `max_pages` ceiling (default 200) + seen-token cycle guard.

**SEC-1 · proxy credentials printed to logs — `cli/bootstrap.py`**
The "mask credentials" line `dsn.split('@')[0]` keeps the whole userinfo *including the password* before `@`, so the DSN password was printed verbatim. **Fix:** `_mask_dsn()` via `urlsplit`, redacting the password component.

**HYG-1 · orphaned importable bytecode — `portals/aramisauto_com/`**
Directory held only `__pycache__/__init__.cpython-310.pyc` (no source, untracked by git, zero code references) — stale, un-auditable bytecode that can still satisfy an import on a matching cache tag. **Fix:** directory removed. The live scraper is `aramisauto_fr`.

### 2.3 MEDIUM (fixed)

- **`discovery/quality_sample.py`** — guarded the MeiliSearch `/stats` GET status before `.json()` (an error response aborted the sampler).
- **`discovery/meili_enricher.py`** — module docstring made a raw string (`r"""`) to clear an `invalid escape sequence '\d'` `DeprecationWarning` (a future `SyntaxError`).

### 2.4 New shared utility

**`common/net_guard.py`** (new) — `is_safe_public_url(url, *, resolve=False)`. Rejects non-http(s) schemes, missing hosts, IP-literal hosts in private/loopback/link-local/reserved/multicast/unspecified ranges (covers `169.254.169.254` and all RFC1918), and internal names (`localhost`, `*.localhost`, `*.internal`, `*.local`, single-label hosts). `resolve=True` additionally rejects DNS names resolving to a non-public address (DNS-rebinding), failing closed on resolution error. Default `resolve=False` keeps the discovery hot paths non-blocking and test-compatible while still closing every IP-literal/internal-name vector.

---

## 3. Documented — owner decision required (precise fix included)

These are real findings deliberately **not** auto-applied because the fix changes operational behavior of a safety control, a rate budget, a pagination contract, or an upstream API contract — i.e. high-impact / not cleanly reversible. Each carries a ready-to-apply remediation.

### 3.1 HIGH

**ENG-1 · proxy `ban_count_24h` never decays — `engine/proxy/health.py` `record_ban`**
The counter named "24h" is monotonic — nothing ages out old bans. After 3 lifetime bans a proxy is quarantined permanently, so the residential pool **silently shrinks toward zero** over time. *Fix:* compute the window from `last_ban_at` (column already exists) — store ban timestamps or decay `ban_count_24h` when `now - last_ban_at > 86400`. **Behavioral change to production proxy rotation → needs sign-off.**

**ENG-2 · browser launch has no timeout + leak on partial construction — `engine/antidetect/browser.py`, `engine/session/warming.py`**
`AsyncCamoufox(...)` / `new_page()` launches have no `asyncio.wait_for`; a wedged launch through a dead residential proxy hangs the single-threaded coordinator/warming daemon indefinitely, and a failure between `__aenter__` and slot registration leaks the browser process. In `warming.py`, a silent `storage_state()` acquisition failure can strand an identity in `WARMING` forever. *Fix:* `asyncio.wait_for` every launch; unwind partial construction in `except`; surface persistent storageState failures instead of looping.

**ENG-3 · proxy credentials in a loggable URL — `engine/proxy/pool.py` `Proxy.url`**
`f"http://{user}:{password}@{ip}:{port}"` interpolates the residential-proxy secret into a string that flows into sessions/probes; any `log` of it leaks the credential. *Fix:* add a redacting `__repr__`; never log `Proxy.url`; prefer the separate-field `playwright_dict` form for diagnostics.

**AGG-1 · API key sent as URL query parameter — `aggregators/auto_api.py`, `aggregators/transport.py`**
`params = {"api_key": api_key, ...}` puts the secret in the query string; combined with `AggregatorError` surfacing response bodies and the DLQ storing `last_error`, this is a realistic key-disclosure path. `carapis.py` correctly uses a `Bearer` header. *Fix:* prefer header auth where the upstream allows; otherwise redact `api_key=` from any URL/body before logging or persisting. **Upstream contract → confirm before switching auth mode.**

**RATE-1 · rate limit 2–4× over the 0.3 req/s budget — `common/autoscout24.py` (`_SLEEP_BASE=1.2`), `discovery/sources/trustpilot.py` (0.5 s/page)**
Inter-request delay is below the contracted 0.3 req/s/domain ceiling (~3.33 s). *Fix:* raise the base delay to ≥3.33 s or route through a per-domain token bucket. **Throughput/ops tuning → owner sets the budget.**

**DATA-1 · within-page dedup truncates segments — `portals/base.py` `_paginate`, worst case `portals/autotrack_nl`**
The exhaustion test compares `len(extracted_unique) < PAGE_SIZE`, but most `_extract` implementations dedup within the page; any sponsored/duplicate card on a *full* page makes the unique count fall below `PAGE_SIZE` and terminates the segment early. `autotrack_nl` (28 unique of 30/page) collapses a 220k-inventory sweep to ~28 URLs/cycle. *Fix:* have `fetch_segment`/`_extract` report the raw card count separately and test exhaustion on that, or set `PAGE_SIZE` to the minimum observed unique-per-page. **Pagination-contract change across the fleet → verify portal-by-portal.**

### 3.2 MEDIUM

**ENG-4 · non-atomic read-modify-write on SQLite (10 sites)** — `identity/store.py::update_trust`, `identity/aging.py::record_hard_block`, `proxy/health.py::record_result`/`record_ban`, `router/circuit.py::record_failure`/`record_success`, `router/escalator.py::escalate`, `proxy/affinity.py::set_affine_proxy`, `antidetect/sensor.py::store_token`, `session/state.py::save`, `session/warming.py::_record_progress`. Each does `SELECT → compute → UPDATE` (or two UPDATEs) without a transaction → lost updates under concurrency, corrupting the "identity-as-financial-asset" trust ledger and the breaker/EWMA safety signals. Currently MEDIUM because the coordinator runs a single loop (one writer). **Note:** the DB opens with `isolation_level=None` (autocommit), so a naïve `with conn:` is a *no-op* for atomicity — the correct fix is an explicit `BEGIN IMMEDIATE … COMMIT` around each read-modify-write (and in-SQL increments where the prior value isn't needed). Deferred to avoid subtle transaction-semantics regressions across all 10 sites in one sweep.

**OBS-1 · Prometheus label cardinality — `engine/monitoring/metrics.py`** — gauges labeled by `identity_id` and `proxy_ip` retain a child series per unique value forever; a long-running fleet that churns identities and rotates residential IPs grows the registry without bound (memory leak + `/metrics` bloat). *Fix:* drop the high-cardinality labels (aggregate by country/tier/provider/status) or `.remove(...)` the series on identity retire / permanent proxy quarantine.

**RACE-1 · lazy `_build_id` resolution race — `portals/{anibis_ch, tutti_ch, autokopen_nl, carvago_com}`** — the Next.js `_next/data` build-id is resolved lazily into shared instance state with no lock; concurrent segment tasks double-resolve / clobber. *Fix:* resolve once in `run()` before pagination, or guard with an `asyncio.Lock`. (Verify the coordinator instantiates a fresh scraper per cycle.)

**SEC-2 · untrusted-HTML parsing without size/recursion caps — `pipeline/parse.py`, `pipeline/generic_extractor.py` (gzip), `intelligence/poison.py`** — JSON-LD/meta regexes run with `re.DOTALL` over uncapped HTML; `_walk` recurses untrusted JSON-LD with no depth limit (`RecursionError`); `gzip.decompress` of a `.gz` sitemap has no expansion cap (decompression bomb); `poison._visible_text` is computed twice per page. *Fix:* cap input length before regex/JSON; bound `_walk` depth; stream-decompress gz with a ceiling (`zlib.decompressobj`); compute visible text once.

**DATA-2 · `indexer.delta` PG/Redis non-atomicity + mojibake — `common/indexer.py`** — PG INSERT/DELETE and the Redis `xadd` are not atomic and PG-first; a failed `xadd` leaves a row indexed but never enriched (and never re-streamed next cycle). The source file also carries UTF-8 mojibake in comments (toolchain re-encoding defect). `delta` is a split read-modify-write across autocommit connections assuming a single-writer-per-portal invariant that isn't enforced. *Fix:* stream to Redis (idempotent `xadd`) before/with the PG write inside one `conn.transaction()`, document/enforce single-writer-per-portal, re-save the file as clean UTF-8.

**ANTI-1 · `navigator.languages` incoherent with locale — `common/pw_base.py` `_STEALTH_JS`** — the Chromium-fallback stealth script hardcodes `['de-DE','de','en-US','en']` while the context `locale`/`Accept-Language` are parametrized → for FR/ES/NL the JS-exposed languages contradict the headers (a bot signal). *Fix:* template the language array from `locale`.

**SEC-3 · query-DSL string interpolation — `portals/auto_selection_com` (Meilisearch filter), `portals/autohero_com` (GraphQL)** — filter/query strings built by f-string interpolation of brand/country; inputs are from fixed allowlists today (not exploitable) but fragile. *Fix:* parameterize (GraphQL `variables`) / escape and validate against the allowlist.

**SCRAPE-1 · speculative `[ASSUMED]`/`[INFERRED]` listing regexes (~12 portals)** — `auto_de`, `autohaus24_de`, `autohus_de`, `autowereld_nl`, `buscocoches_com`, `belgiemobiel_be`, `myway_be`, `vroom_be`, `youcar_be`, `pkw_de` (targets the `/autokatalog/` spec surface, not used-listings), `reezocar_fr`, `spoticar_fr`, `aramisauto_fr`: broad regexes over unverified URL shapes emit facet/category/pagination/off-domain URLs as "listings" until live-verified. *Fix:* verify each detail-URL shape against live HTML and tighten (anchor on a numeric/UUID id).

**SCRAPE-2 · disabled cap-recovery silently truncates (~5 portals)** — `moniteur_auto_be`, `pkw_de`, `truckscout24_com`, `vroom_be` (and `flexicar_es` single-segment): brand/category partition with `MAX_PAGES≈50` and `subdivide_segment` returning `[]` loses everything beyond ~1000 listings for high-volume segments. *Fix:* implement price/year subdivision for capped segments.

**SCRAPE-3 · cross-language double-emit — `portals/gocar_be`** — the same listing appears under both `/nl/` and `/fr/` paths; URL-level dedup can't collapse them → every car emitted twice. *Fix:* dedup on the extracted listing id, or scrape one language.

**MISC (MEDIUM, documented):** loose msgpack hand-encoder needs a byte-equality unit test vs `msgpack` (`tutti_ch`); `largus_fr` dedup key includes the non-stable slug (re-emits the same UUID); `dlq.py`/`transport.py` `Retry-After` parse rejects the HTTP-date form; `aggregators/auto_api.py` `SOURCE_SLUGS` allowlist defined but unenforced (path interpolation of `source`); `mobile_re/interceptor.py`/`mapper.py` stubs need `package_name`/`portal` sanitization (path-traversal/JS-injection) and `yaml.safe_load` before implementation.

### 3.3 Anti-detection / UA policy — needs a product ruling (NOT auto-changed)

Per `CONTEXT_FOR_AI.md`, the stealth marketplace fleet must not override the UA. The analysis flagged literal/rotating UAs in: `discovery/frontier_runner.py`, `discovery/dealer_classifier.py`, `discovery/wp_rest_harvester.py`, `discovery/sources/ddg_resolver.py`, `discovery/sources/bovag.py`, `discovery/sources/portal_aggregator.py` (all `httpx` discovery crawlers), and `portals/wallapop_com` (hardcoded mobile UA). **These were deliberately not stripped:** for the *polite identifying* discovery crawlers, an explicit `CardexBot` UA is arguably correct (matches the Go discovery layer's transparency policy and robots identification), and `wallapop`'s mobile UA is *required* by its mobile API. Stripping them blindly could break politeness/identification or the mobile endpoint. **Decision needed:** confirm which layer each module belongs to; where it is the stealth fleet, route the UA through the identity/profile store (rotated, JA3-coherent) rather than a module constant. `geocode.py`'s identifying Nominatim UA is *required by ToS* — keep.

---

## 4. Clean / well-hardened (sampled)

No CRITICAL/HIGH issues, correct patterns: `engine/router/domain_map.py`, `engine/proxy/tiers.py`, `engine/session/intent.py`, `engine/monitoring/softblock.py`, `engine/identity/profile.py`, `pipeline/{delta,quality,schema}.py`, `intelligence/waf.py`, and ~18 portal scrapers using the shared `_get`/retry/dedup pattern with JSON type-checks (`autoboerse_de`, `autocasion_com`, `autolina_ch`, `coches_net`, `comparis_ch`, `deuxememain_be`, `heycar_com`, `kleinanzeigen_de`, `lacentrale_fr`, `leboncoin_fr`, the five AS24 country packages, …). **No `eval`/`exec`/`pickle`/`yaml.load`/`verify=False`/`os.system`/`subprocess` anywhere in the tree.** No scraper creates its own session (JA3 coherence preserved) except where flagged.

---

## 5. Pre-existing issues (NOT regressions from this audit)

1. **`test_t1_registry_resolves_both_portals` FAILS at baseline** — `get_scraper("autotrack.nl")` returns `portals.autotrack_nl.AutoTrackNLScraper` but the test expects `portals.nl.autotrack.AutotrackNL`. **Two autotrack implementations** (different base classes) exist for one domain; the registry and the test disagree. Same duplicate-class hazard exists for coches.net (`portals/cochesnet.py` vs `portals/coches_net/__init__.py`, both `CochesNetScraper`). *Resolution needs the owner to declare the canonical implementation and delete the stale one* — not changed here to avoid altering dispatch.
2. **`discovery/sitemap_bridge.py` does not import** — `from scrapers.sitemap_indexer import …` references a "sealed" module removed in commit `1ec6ad5` and absent from the checkout (`ModuleNotFoundError`). Pre-existing at HEAD (verified via `git show HEAD`); the SSRF guard added here is correct for when that module is restored, but the entrypoint is currently dead.

---

## 6. Verification

- **Tests:** `python -m pytest scrapers/tests/` → `1 failed, 1308 passed` before and after (the 1 failure is §5.1, pre-existing). Targeted: `test_generic_extractor` + `test_discovery_modules` (86) green with the SSRF guards; `-k phase` (785) green with the portal transport guards.
- **Compile:** `py_compile` passes on all 35 changed files.
- **Import smoke-test:** all changed modules import cleanly except `sitemap_bridge.py` (pre-existing, §5.2).
- **Logic-preservation:** large diffs (`repair_pass`, `bovag`, `fr_sirene_v311`, …) are re-indentation from wrapping bodies in `try/finally`; `git diff -w` confirms the only semantic additions are `try:`/`finally:`/guards — no SQL, regex, batching, rate-limit, or pagination changes.

## 7. Files changed (35)

`common/net_guard.py` (new), `common/doc_converter.py`, `common/pw_base.py`, `cli/bootstrap.py`, `engine/router/classifier.py`, `pipeline/normalize.py`, `pipeline/generic_extractor.py`, `mobile_re/client.py`, `discovery/{name_to_domain, meili_enricher, meili_bridge, repair_pass, orphan_backfill, quality_gate, quality_sample, sitemap_resolver, sitemap_bridge, sitemap_image_harvester, wp_rest_harvester}.py`, `discovery/sources/{ct_logs, fr_sirene_v311, osm_expanded_run, sirene_standalone, as24_curl_cffi, bovag, trustpilot}.py`, `portals/{autoweek_nl, caravenue_com, classic_trader_com, coches_com, gocar_be, milanuncios_com, simplicicar_com, truckscout24_com, zoomcar_fr}/__init__.py`, and removed orphaned `portals/aramisauto_com/`.

---
*Generated by the CARDEX scraper security & robustness audit, 2026-06-05.*
