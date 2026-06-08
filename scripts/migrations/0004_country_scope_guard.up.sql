-- 0004_country_scope_guard.up.sql
-- BUSINESS INVARIANT (DB-enforced): the territory is STRICTLY 6 countries —
--   ES, FR, DE, BE, NL, CH.
-- A runaway writer (e.g. the discovery session) keeps trying to insert IT/AT/PT/PL.
-- This trigger silently DISCARDS any out-of-scope row (RETURN NULL) on the three
-- inventory tables, so the writer never errors but the data can never be contaminated.
-- Out-of-scope = country not in the 6, OR the domain/source_domain TLD is .it/.at/.pt/.pl.
-- Reversible: see 0004_country_scope_guard.down.sql.

BEGIN;

CREATE OR REPLACE FUNCTION enforce_country_scope() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  c text;
  d text;
BEGIN
  -- country guard (all three tables carry a CHAR(2) country)
  c := upper(btrim(coalesce(NEW.country::text, '')));
  IF c <> '' AND c NOT IN ('ES', 'FR', 'DE', 'BE', 'NL', 'CH') THEN
    RETURN NULL;                      -- silently drop: writer sees no error, row not written
  END IF;

  -- TLD guard on the domain-like column (name differs per table)
  IF TG_TABLE_NAME = 'vehicle_index' THEN
    d := lower(coalesce(NEW.source_domain, ''));
  ELSE
    d := lower(coalesce(NEW.domain, ''));
  END IF;
  IF d ~ '\.(it|at|pt|pl)$' THEN      -- anchored to the real TLD, not a substring/subdomain
    RETURN NULL;
  END IF;

  RETURN NEW;                          -- in scope → allow
END;
$$;

DROP TRIGGER IF EXISTS trg_scope_guard ON discovery_candidates;
CREATE TRIGGER trg_scope_guard BEFORE INSERT OR UPDATE ON discovery_candidates
  FOR EACH ROW EXECUTE FUNCTION enforce_country_scope();

DROP TRIGGER IF EXISTS trg_scope_guard ON source_entities;
CREATE TRIGGER trg_scope_guard BEFORE INSERT OR UPDATE ON source_entities
  FOR EACH ROW EXECUTE FUNCTION enforce_country_scope();

DROP TRIGGER IF EXISTS trg_scope_guard ON vehicle_index;
CREATE TRIGGER trg_scope_guard BEFORE INSERT OR UPDATE ON vehicle_index
  FOR EACH ROW EXECUTE FUNCTION enforce_country_scope();

COMMIT;
