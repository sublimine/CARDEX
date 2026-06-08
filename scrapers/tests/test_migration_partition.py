"""
vehicle_events partition migration — abort-safety must not depend on a CLI flag.

The script used to rely on ``psql --single-transaction`` for atomicity; forget the
flag and a mid-script failure leaves a half-migrated schema. It is now wrapped in an
explicit ``BEGIN; … COMMIT;`` so it rolls back on ANY failure however it is invoked.

  * structural: the file opens with BEGIN, ends with COMMIT, and keeps the row-count
    RAISE verify between them.
  * behavioural (live PG, throwaway table, NO --single-transaction): an explicit
    BEGIN/…/RAISE/COMMIT script rolls the whole thing back — proving the pattern, not
    the flag, gives abort-safety. (The real file targets prod ``vehicle_events`` and is
    never executed here.)
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg
import pytest

_SQL = (Path(__file__).resolve().parents[2] / "scripts" / "migrate_vehicle_events_partition.sql")
_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")


@pytest.mark.unit
def test_migration_is_explicitly_transactional():
    text = _SQL.read_text(encoding="utf-8")
    # statements (ignore comment/blank lines) must open with BEGIN and close with COMMIT
    stmts = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("--")]
    assert stmts[0].upper().startswith("BEGIN"), stmts[0]
    assert stmts[-1].upper().startswith("COMMIT"), stmts[-1]
    # the atomic row-count verify is still inside the transaction
    assert "RAISE EXCEPTION" in text and "ROW COUNT MISMATCH" in text
    begin_i = text.upper().index("BEGIN;")
    commit_i = text.upper().rindex("COMMIT;")
    assert begin_i < text.index("ALTER TABLE vehicle_events") < commit_i


@pytest.mark.integration
def test_explicit_begin_commit_rolls_back_on_failure_without_flag():
    async def go():
        try:
            conn = await asyncpg.connect(_DSN, timeout=10)
        except Exception:  # noqa: BLE001
            pytest.skip("postgres not available")
        tbl = "_p2_mig_probe"
        # Same shape as the real script: explicit BEGIN, work, a failing verify, COMMIT.
        # Run WITHOUT --single-transaction (asyncpg adds no such flag).
        script = (
            f"BEGIN;\n"
            f"CREATE TABLE {tbl} (id int);\n"
            f"INSERT INTO {tbl} VALUES (1);\n"
            f"DO $$ BEGIN RAISE EXCEPTION 'deliberate verify failure'; END $$;\n"
            f"COMMIT;\n"
        )
        try:
            await conn.execute(f"DROP TABLE IF EXISTS {tbl}")
            with pytest.raises(asyncpg.PostgresError):
                await conn.execute(script)
            # The RAISE aborted the explicit transaction; COMMIT on an aborted block is
            # a no-op rollback. Clear the client state, then prove NOTHING persisted.
            await conn.execute("ROLLBACK")
            exists = await conn.fetchval("SELECT to_regclass($1)", tbl)
            assert exists is None
        finally:
            try:
                await conn.execute("ROLLBACK")
            except Exception:  # noqa: BLE001
                pass
            await conn.execute(f"DROP TABLE IF EXISTS {tbl}")
            await conn.close()

    asyncio.run(go())
