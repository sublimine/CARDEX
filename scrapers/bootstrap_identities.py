"""Identity bootstrap — provision the engine.db identity pool before the coordinator runs.

One idempotent step that:
  1. opens/creates the SQLite engine.db (ENGINE_DB_PATH) and migrates its schema,
  2. mints DIRECT identities for every country (unblocks T0/T1 — open APIs, no proxy),
  3. mints RESIDENTIAL identities from RESIDENTIAL_PROXY_<CC> env (unblocks T2/T3 giants).

Run as a compose init step (shared engine.db volume) so every coordinator container picks
the same warmed pool:  python -m scrapers.bootstrap_identities
"""
from __future__ import annotations

import logging
import os

from scrapers.db import connect, migrate
from scrapers.engine.identity.direct import ensure_direct_identities
from scrapers.engine.identity.residential import ensure_residential_identities

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db_path = os.environ.get("ENGINE_DB_PATH", "scrapers/engine.db")
    conn = connect(db_path)
    try:
        migrate(conn)
        direct = ensure_direct_identities(conn)
        residential = ensure_residential_identities(conn, os.environ)
        log.info("identity bootstrap: db=%s direct_created=%d residential_provisioned=%d",
                 db_path, direct, residential)
        if residential == 0:
            log.warning("no RESIDENTIAL_PROXY_<CC> set — T2/T3 (defended) portals will park "
                        "on NO_IDENTITY until a residential proxy is supplied")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
