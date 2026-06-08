-- 0005_country_scope_check_constraint.up.sql  (idempotent — safe to re-apply)
-- ROOT CAUSE of the guard failure (PL 8535 / AT 303 / IT 290 re-entered after 0004):
--   another session ran CREATE OR REPLACE FUNCTION enforce_country_scope() and WIDENED the
--   allow-list to 10 countries ("original 6 + expanded IT/AT/PT/PL"). A trigger FUNCTION is
--   overwritable; the trigger fired but called a function that now permitted PL/AT/IT.
-- FIX: CHECK CONSTRAINTS cannot be silently overwritten by CREATE OR REPLACE FUNCTION (they
--   must be explicitly DROPped), are enforced under COPY/bulk, and under
--   session_replication_role='replica' (where ORIGIN triggers are skipped). The constraint
--   guards BOTH country (not in the 6) AND domain TLD (.it/.at/.pt/.pl) so it holds even if
--   the trigger function is tampered. Defense in depth: restore the strict function + make the
--   triggers ENABLE ALWAYS. Reversible: see down.sql.

BEGIN;

-- 1. Restore the STRICT 6-country function (+ TLD guard).
CREATE OR REPLACE FUNCTION enforce_country_scope() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  c text;
  d text;
BEGIN
  c := upper(btrim(coalesce(NEW.country::text, '')));
  IF c <> '' AND c NOT IN ('ES', 'FR', 'DE', 'BE', 'NL', 'CH') THEN
    RETURN NULL;
  END IF;
  IF TG_TABLE_NAME = 'vehicle_index' THEN
    d := lower(coalesce(NEW.source_domain, ''));
  ELSE
    d := lower(coalesce(NEW.domain, ''));
  END IF;
  IF d ~ '\.(it|at|pt|pl)$' THEN
    RETURN NULL;
  END IF;
  RETURN NEW;
END;
$$;

-- 2. Fire the triggers even under session_replication_role='replica'.
ALTER TABLE discovery_candidates ENABLE ALWAYS TRIGGER trg_scope_guard;
ALTER TABLE source_entities      ENABLE ALWAYS TRIGGER trg_scope_guard;
ALTER TABLE vehicle_index        ENABLE ALWAYS TRIGGER trg_scope_guard;

-- 3. Purge any out-of-scope row (country OR domain TLD) so the CHECKs validate clean.
DELETE FROM vehicle_index
  WHERE country NOT IN ('ES','FR','DE','BE','NL','CH')
     OR lower(coalesce(source_domain,'')) ~ '\.(it|at|pt|pl)$';
DELETE FROM source_entities
  WHERE (country IS NOT NULL AND country NOT IN ('ES','FR','DE','BE','NL','CH'))
     OR lower(coalesce(domain,'')) ~ '\.(it|at|pt|pl)$';
DELETE FROM discovery_candidates
  WHERE country NOT IN ('ES','FR','DE','BE','NL','CH')
     OR lower(coalesce(domain,'')) ~ '\.(it|at|pt|pl)$';

-- 4. The un-overwritable hard guard: country in the 6 AND domain TLD not out-of-scope.
ALTER TABLE discovery_candidates DROP CONSTRAINT IF EXISTS chk_country_scope;
ALTER TABLE discovery_candidates ADD CONSTRAINT chk_country_scope CHECK (
  country IN ('ES','FR','DE','BE','NL','CH')
  AND (domain IS NULL OR lower(domain) !~ '\.(it|at|pt|pl)$'));

ALTER TABLE source_entities DROP CONSTRAINT IF EXISTS chk_country_scope;
ALTER TABLE source_entities ADD CONSTRAINT chk_country_scope CHECK (
  (country IS NULL OR country IN ('ES','FR','DE','BE','NL','CH'))
  AND (domain IS NULL OR lower(domain) !~ '\.(it|at|pt|pl)$'));

ALTER TABLE vehicle_index DROP CONSTRAINT IF EXISTS chk_country_scope;
ALTER TABLE vehicle_index ADD CONSTRAINT chk_country_scope CHECK (
  country IN ('ES','FR','DE','BE','NL','CH')
  AND (source_domain IS NULL OR lower(source_domain) !~ '\.(it|at|pt|pl)$'));

COMMIT;
