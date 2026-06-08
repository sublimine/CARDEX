"""Residential-proxy identity provisioning — enables T2/T3 (defended) portals.

T2/T3 portals (Akamai/DataDome/Cloudflare-Pro) require a *proxied* identity
(`proxy_tiers.requires_proxy` → True), so with only DIRECT identities the coordinator
parks every giant on NO_IDENTITY. This module turns a per-country residential-proxy
credential — supplied as the env var ``RESIDENTIAL_PROXY_<CC>`` — into an active,
premium-trust, RESIDENTIAL_ROTATING identity the coordinator can pick for that country's
T2/T3 jobs (lacentrale, milanuncios, nederlandmobiel, promoneuve, mobile.de, …).

When Elias fills ``RESIDENTIAL_PROXY_FR=http://user:pass@host:port`` and re-runs the
bootstrap, FR's defended portals start getting a proxied identity automatically.

Idempotent: ids are derived deterministically from (country, index). A new run creates
missing identities and refreshes the proxy URL of existing ones WITHOUT resetting their
trust lifecycle (owned by aging.py).

NOTE — honest scope: a residential IP is *necessary* but not *sufficient* for DataDome.
The runtime Camoufox warming still has to solve the challenge per session; this module
makes the proxy available and the identity pickable. Whether a given T3 portal actually
cracks is validated live on the VPS.
"""
from __future__ import annotations

import dataclasses
import sqlite3
import time
import uuid
from typing import Mapping

from scrapers.engine.identity import store
from scrapers.engine.identity.profile import (
    COUNTRY_TIMEZONES,
    IdentityStatus,
    ProxyTier,
    generate_direct,
)

# Distinct namespace from direct identities so the two pools never collide.
_RES_NS = uuid.UUID("cade0001-0000-4000-8000-000000000000")

# Above the 7.0 premium gate so a residential identity qualifies for T3 (DataDome).
_RES_TRUST = 8.0
DEFAULT_PER_COUNTRY = 2
ENV_PREFIX = "RESIDENTIAL_PROXY_"


def _res_id(country: str, index: int) -> str:
    return str(uuid.uuid5(_RES_NS, f"residential:{country}:{index}"))


def ensure_residential_identities(
    conn: sqlite3.Connection,
    env: Mapping[str, str],
    per_country: int = DEFAULT_PER_COUNTRY,
) -> int:
    """Provision residential identities from ``RESIDENTIAL_PROXY_<CC>`` env vars.

    Returns the number of identities created or updated. Countries with no env var are
    skipped (their T2/T3 jobs stay on NO_IDENTITY until a proxy is supplied).
    """
    now = int(time.time())
    pending: list = []
    for country in COUNTRY_TIMEZONES:
        proxy_url = (env.get(ENV_PREFIX + country) or "").strip()
        if not proxy_url:
            continue
        for index in range(per_country):
            iid = _res_id(country, index)
            existing = store.get(conn, iid)
            if existing is not None:
                if existing.proxy_ip == proxy_url:
                    continue  # unchanged — leave its trust lifecycle intact
                # proxy URL changed: refresh it, preserve the rest of the lifecycle
                pending.append(dataclasses.replace(existing, proxy_ip=proxy_url))
                continue
            pending.append(dataclasses.replace(
                generate_direct(country, identity_id=iid),
                proxy_ip=proxy_url,
                proxy_tier=ProxyTier.RESIDENTIAL_ROTATING,
                proxy_provider="residential_env",
                status=IdentityStatus.ACTIVE,
                warming_done=True,
                trust_score=_RES_TRUST,
                created_at=now,
            ))

    if not pending:
        return 0

    conn.execute("BEGIN")
    try:
        for identity in pending:
            store.save(conn, identity)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return len(pending)
