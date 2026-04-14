# Schema Audit Report — Knowledge Graph SQLite
**Date:** 2026-04-14  
**Files audited:** `discovery/internal/db/schema.sql`, `discovery/internal/db/migrate.go`,
`discovery/internal/kg/dealer.go`, `discovery/internal/kg/webpresence.go`  
**Auditor:** Internal (automated pass)  
**Severity scale:** CRITICAL > HIGH > MEDIUM > LOW

---

## Executive Summary

The base schema is structurally sound with appropriate ULID PKs, FK declarations,
and WAL mode. Two CRITICAL issues: the `rate_limit_state` table bypasses the
migration framework entirely and the `dealer_location` table has no deduplication
constraint, enabling unbounded row accumulation. Five HIGH and six MEDIUM issues
relate to missing indices, incomplete FK cascade rules, misleading comments, and
migration reversibility.

---

## CRITICAL

### S-C1 — `rate_limit_state` table is not in `schema.sql` or any migration
**File:** `passive_dns/hackertarget.go:244-249`  
**Finding:**  
```go
const rateLimitTableSQL = `
CREATE TABLE IF NOT EXISTS rate_limit_state (
  api_name     TEXT PRIMARY KEY,
  reqs_today   INTEGER NOT NULL DEFAULT 0,
  window_start TEXT NOT NULL
);`

func (h *HackerTarget) ensureRateLimitTable(ctx context.Context) error {
    _, err := h.db.ExecContext(ctx, rateLimitTableSQL)
    return err
}
```

This table is created inline by application logic, bypassing the versioned
migration framework. Consequences:

1. The table is not listed in `schema.sql`, so the canonical schema document
   is incomplete.
2. `schema_version` has no record of this table's existence. Tools that
   reconstruct schema from `schema_version` will miss it.
3. If the `discovery` module is later split into microservices, each service
   that imports `hackertarget.go` will independently create this table in
   whatever DB it connects to, possibly the wrong DB.
4. The table is also needed by `nl_kvk` (referenced in KvK sub-technique
   comments) but the `ensureRateLimitTable` logic lives only in `hackertarget.go`.

**Fix:** Add migration v4 that creates `rate_limit_state`. Remove
`ensureRateLimitTable` from `hackertarget.go`. Add `schema.sql` entry.

---

### S-C2 — `dealer_location` has no deduplication constraint
**File:** `schema.sql:52-71`  
**Finding:**  
```sql
CREATE TABLE IF NOT EXISTS dealer_location (
  location_id  TEXT PRIMARY KEY,
  dealer_id    TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  is_primary   BOOLEAN NOT NULL DEFAULT 1,
  address_line1 TEXT,
  ...
);
-- No UNIQUE INDEX on (dealer_id, address_line1) or (dealer_id, is_primary)
```

Combined with `dealer.go:86` which generates a new ULID for `location_id` on
every call, `INSERT OR IGNORE` in `AddLocation` **never fires** — the PK is
always unique. Every discovery cycle for a known dealer inserts a new location
row with identical data. After N cycles, a dealer has N identical rows.

**Impact:** Data correctness, query correctness (`SELECT ... WHERE is_primary=1`
returns N rows for a single dealer), storage bloat.

**Fix:**
```sql
-- Migration v5
CREATE UNIQUE INDEX IF NOT EXISTS idx_location_dealer_addr
  ON dealer_location(dealer_id, address_line1, country_code);
```
Change `AddLocation` to `INSERT OR IGNORE INTO dealer_location ... ON CONFLICT DO UPDATE SET phone = excluded.phone, ...`

---

## HIGH

### S-H1 — Schema documentation is out of sync with actual schema post-migrations
**Files:** `schema.sql`, `migrate.go`  
**Finding:**  
`schema.sql` is the "AUTHORITATIVE" document but does not include:

- `dealer_web_presence.metadata_json` (added in migration v2)
- `dealer_location.phone` (added in migration v3)
- `rate_limit_state` table (added inline, never in schema)

A developer reading `schema.sql` sees an incomplete picture. The "v1" comment
on `schema.sql` is accurate but misleading: the file is presented as the
full schema, not just the baseline.

**Fix:** Add a comment at the top: "Base schema v1 — see migrate.go for
incremental additions." Or regenerate `schema.sql` as the cumulative schema
after each migration (preferred for documentation clarity).

---

### S-H2 — No `ON DELETE CASCADE` on child tables
**File:** `schema.sql` (all FK declarations)  
**Finding:**  
All foreign key constraints omit `ON DELETE` behavior:
```sql
dealer_id TEXT NOT NULL REFERENCES dealer_entity(dealer_id)
-- missing: ON DELETE CASCADE or ON DELETE RESTRICT
```

SQLite's default FK action is `NO ACTION` (the delete is rejected if the parent
row is referenced). This means deleting a `dealer_entity` row will fail silently
(since `PRAGMA foreign_keys = ON` is set but FK errors are not always propagated).
More critically, if a dealer deduplication pass needs to merge two entities and
delete the duplicate, child rows (identifiers, locations, web presences,
discovery records) must be manually deleted first.

**Assessment:** No delete operations currently exist in application code, making
this LOW in practice. But it becomes HIGH risk when a deduplication/merge pass
is implemented in Phase 2 saturation protocol.

**Fix:** Add `ON DELETE CASCADE` to all child FK references, or create a
`deleteDealer(ctx, dealerID)` function that deletes children before the parent.

---

### S-H3 — `schema_version` has no PRIMARY KEY on `version`
**File:** `schema.sql:9-13`  
```sql
CREATE TABLE IF NOT EXISTS schema_version (
  version     INTEGER NOT NULL,
  applied_at  TIMESTAMP NOT NULL DEFAULT ...,
  description TEXT
);
```
No PRIMARY KEY or UNIQUE INDEX on `version`. The base schema's:
```sql
INSERT OR IGNORE INTO schema_version(version, description) VALUES (1, '...');
```
...has no constraint to ignore against, so `INSERT OR IGNORE` behaves as plain
`INSERT`. If the base schema were applied twice (hypothetically), two v1 rows
would exist. The migration guard `SELECT COUNT(*) WHERE version = ?` handles
this correctly (count ≥ 1 skips), but the design intent (one row per version)
is not schema-enforced.

**Fix:** `version INTEGER PRIMARY KEY` in `schema_version`.

---

### S-H4 — `discovery_record` comment claims idempotency that doesn't exist
**File:** `kg/dealer.go:119`, `schema.sql:136-146`  
**Finding:**  
Comment on `RecordDiscovery`:
> "INSERT OR IGNORE — duplicate (dealer, family, sub_technique, discovered_at)
> combinations are dropped silently."

There is **no UNIQUE INDEX** on `(dealer_id, family, sub_technique)` or on
any combination including `discovered_at`. The OR IGNORE only fires on PK
(`record_id`) conflict. Since `record_id` is always a fresh ULID, every call
inserts a new row. The comment describes intended behavior that was never
implemented.

`discovery_record` is designed as an audit log (unlimited rows expected), so
the behavior is arguably correct. But the false comment creates confusion about
whether idempotency is guaranteed.

**Fix:** Remove the misleading comment. If idempotent-per-cycle behavior is
desired, add a UNIQUE INDEX on `(dealer_id, family, sub_technique)` and use
`ON CONFLICT DO UPDATE SET last_reconfirmed_at = excluded.discovered_at`.

---

### S-H5 — Missing index on `dealer_association_membership.dealer_id`
**File:** `schema.sql:124-134`  
```sql
CREATE TABLE IF NOT EXISTS dealer_association_membership (
  membership_id   TEXT PRIMARY KEY,
  dealer_id       TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
  ...
);
-- No index on dealer_id
```
All other child tables have `idx_xxx_dealer` covering their `dealer_id`
foreign key. `dealer_association_membership` is the exception. Queries like
`SELECT * FROM dealer_association_membership WHERE dealer_id = ?` require
full table scan.

Same issue applies to `dealer_chain_membership.dealer_id` — the composite
PRIMARY KEY `(chain_id, dealer_id)` supports lookup by `chain_id` but not
by `dealer_id` alone.

**Fix:**
```sql
CREATE INDEX idx_association_dealer ON dealer_association_membership(dealer_id);
CREATE INDEX idx_chain_member_dealer ON dealer_chain_membership(dealer_id);
```

---

## MEDIUM

### S-M1 — No DOWN migrations (zero reversibility)
**File:** `migrate.go`  
The incremental migrations struct has only `sql` (UP direction). There is no
rollback path. Once migration v2 or v3 is applied, reverting to an earlier
schema requires restoring from backup. For an `ALTER TABLE ADD COLUMN` this is
acceptable, but future migrations that add NOT NULL columns, rename columns, or
drop tables will be irreversible without DROP and recreate.

**Recommendation:** Document explicitly that migrations are append-only and
irreversible by design. Add a `downSQL` field to the struct even if empty, to
signal awareness. Establish a policy: breaking schema changes require a new DB
file (blue/green) rather than in-place migration.

---

### S-M2 — `BOOLEAN` is stored as INTEGER but not validated
**File:** `schema.sql:55`, `schema.sql:177`  
SQLite has no BOOLEAN type. `is_primary BOOLEAN NOT NULL DEFAULT 1` and
`manual_review_required BOOLEAN` store INTEGER. Application code passes Go
`bool` values which the driver converts to 0/1. But SQLite will accept `SELECT
... WHERE is_primary = 'yes'` without error (returns zero rows). No CHECK
constraint enforces the 0/1 range.

**Fix:** `CHECK (is_primary IN (0,1))` and `CHECK (manual_review_required IN (0,1))`.

---

### S-M3 — `vehicle_record` has no index on `source_url`
**File:** `schema.sql:152-188`  
`source_url TEXT NOT NULL` identifies where the vehicle was found. Lookup by
source URL (e.g., "is this listing already indexed?") requires a full table
scan. With millions of vehicle records, this will be slow.

**Fix:** `CREATE INDEX idx_vehicle_source_url ON vehicle_record(source_url)`.

---

### S-M4 — TEXT columns for enum-like fields have no CHECK constraints
**File:** `schema.sql` throughout  
The following columns accept any string but have a defined set of valid values:

| Table | Column | Valid values |
|-------|--------|-------------|
| `dealer_entity` | `status` | ACTIVE, DORMANT, CLOSED, UNVERIFIED |
| `dealer_entity` | `legal_form` | SARL, GmbH, SAS, NV, ... (open) |
| `dealer_identifier` | `valid_status` | UNKNOWN, VALID, INVALID |
| `dealer_web_presence` | `health_status` | UP, DOWN, TIMEOUT, ... |
| `vehicle_record` | `status` | PENDING_REVIEW, ACTIVE, REJECTED, ... |
| `vehicle_record` | `vat_mode` | INCL, EXCL, MARGIN, ... |

Without CHECK constraints, typos (e.g., `"UNVERIFED"`, `"active"`) silently
enter the database and break queries.

**Fix:** Add CHECK constraints for all finite-value enum columns.

---

### S-M5 — `dealer_web_presence` conflict clause only updates two fields
**File:** `kg/webpresence.go:18-21`  
```sql
ON CONFLICT(domain) DO UPDATE SET
  url_root               = excluded.url_root,
  discovered_by_families = excluded.discovered_by_families
```
On a domain conflict, `platform_type`, `dms_provider`, `extraction_strategy`,
`robots_txt_fetched_at`, `sitemap_url`, `rss_feed_url`, and `last_health_check`
are NOT updated. If Family C discovers a domain already found by Family F, it
cannot add its family ID to `discovered_by_families` without overwriting the
existing F value. The update sets `discovered_by_families = "C"`, erasing the
prior `"F"`.

**Fix:** `discovered_by_families = excluded.discovered_by_families || ',' || dealer_web_presence.discovered_by_families`
(with deduplication via a trigger or application layer).

---

### S-M6 — `vehicle_equipment` has no index beyond the PK
**File:** `schema.sql:213-218`  
```sql
CREATE TABLE IF NOT EXISTS vehicle_equipment (
  vehicle_id     TEXT NOT NULL REFERENCES vehicle_record(vehicle_id),
  equipment_code TEXT NOT NULL,
  PRIMARY KEY (vehicle_id, equipment_code)
);
```
The composite PK supports lookup by `(vehicle_id, equipment_code)` but not
by `equipment_code` alone (e.g., "all vehicles with sunroof"). Phase 4 quality
pipeline will need equipment-based filtering for V18.

**Fix:** `CREATE INDEX idx_equipment_code ON vehicle_equipment(equipment_code)`.

---

## LOW

### S-L1 — `TIMESTAMP` type is stored as TEXT
**File:** `schema.sql` throughout  
SQLite has no native TIMESTAMP type. All timestamp columns are TEXT, storing
ISO-8601 strings. This is the correct approach for SQLite but means:
- Date arithmetic requires `strftime()` in queries
- Timezone bugs can appear if different parts of the code use different format
  strings. Application code uses `"2006-01-02T15:04:05Z"` (UTC). Consistent,
  but not enforced by schema.

---

### S-L2 — `h3_index` column and index are dead weight
**File:** `schema.sql:65,71`  
`h3_index TEXT` is always NULL (Sprint 1 stub per comment in `kg.go:89`).
`CREATE INDEX idx_location_h3` is live but indexes a column of all NULLs.
SQLite excludes NULL values from default indexes, so the index contains zero
entries but still consumes a B-tree root page.

---

### S-L3 — `metadata_json` columns are not queryable without `json_extract()`
**File:** `schema.sql:29, 104`, migration v2  
`dealer_entity.metadata_json` and `dealer_web_presence.metadata_json` store
arbitrary JSON. Any query that needs a field inside the JSON requires
`json_extract()`, which is not indexed. For large tables this degrades to a
full scan with per-row JSON parsing. Future analytics (e.g., "find all domains
with Wayback coverage > 80%") will be slow.

**Recommendation:** Promote frequently-queried JSON fields to dedicated columns
when their structure stabilizes.

---

### S-L4 — No schema migration test
**File:** `db/migrate.go` — no test file for migration logic  
The migration idempotency guarantee ("re-running is safe") is tested only by
reading the code. There is no automated test that:
1. Creates a fresh in-memory DB
2. Applies the full migration chain
3. Verifies `schema_version` contains exactly the right rows
4. Applies migrations again and verifies no duplicate rows or errors

---

## Summary Table

| ID | Severity | Table / File | Issue |
|----|----------|-------------|-------|
| S-C1 | CRITICAL | `rate_limit_state` (not in schema) | Table outside migration framework |
| S-C2 | CRITICAL | `dealer_location` | No dedup constraint → unbounded accumulation |
| S-H1 | HIGH | `schema.sql` | Documentation out of sync with actual schema |
| S-H2 | HIGH | All FK references | No `ON DELETE CASCADE` |
| S-H3 | HIGH | `schema_version` | No PRIMARY KEY on `version` |
| S-H4 | HIGH | `discovery_record` | Misleading idempotency comment |
| S-H5 | HIGH | `dealer_association_membership`, `dealer_chain_membership` | Missing `dealer_id` index |
| S-M1 | MEDIUM | `migrate.go` | No rollback path |
| S-M2 | MEDIUM | `dealer_entity`, `vehicle_record` | BOOLEAN not validated |
| S-M3 | MEDIUM | `vehicle_record` | No index on `source_url` |
| S-M4 | MEDIUM | Multiple tables | No CHECK constraints on enum columns |
| S-M5 | MEDIUM | `dealer_web_presence` | Conflict clause erases prior `discovered_by_families` |
| S-M6 | MEDIUM | `vehicle_equipment` | No index on `equipment_code` |
| S-L1 | LOW | All tables | TIMESTAMP as TEXT (no enforcement) |
| S-L2 | LOW | `dealer_location` | Dead `h3_index` index |
| S-L3 | LOW | `dealer_entity`, `dealer_web_presence` | JSON blobs not indexable |
| S-L4 | LOW | `db/migrate.go` | No migration test |
