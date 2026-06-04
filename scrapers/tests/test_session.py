"""
Unit tests for the session layer: intent, warming, state, conditioning.

Coroutines are driven via asyncio.run() to match the existing sync-only suite
(pytest-asyncio is installed but no asyncio_mode is configured). Integration
seams that touch a real browser (Camoufox) are never exercised here — only the
pure helpers and the DB-backed bookkeeping are unit-tested. behavioral.* sleeps
are monkeypatched to instant no-ops so conditioning runs in microseconds.
"""
from __future__ import annotations

import asyncio
import dataclasses
import random

import pytest

from scrapers.engine.identity import store
from scrapers.engine.session import conditioning, intent, state, warming
from scrapers.engine.session.intent import BuyerPersona, NavigationStep


# ── intent.py ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_personas_cover_six_countries_twenty_each():
    assert set(intent.PERSONAS) == {"DE", "ES", "FR", "NL", "BE", "CH"}
    assert all(len(pool) == 20 for pool in intent.PERSONAS.values())
    assert sum(len(pool) for pool in intent.PERSONAS.values()) == 120


@pytest.mark.unit
def test_persona_ids_are_country_indexed():
    pool = intent.PERSONAS["FR"]
    assert [p.id for p in pool] == [f"FR-{i:02d}" for i in range(20)]
    assert all(p.country == "FR" for p in pool)


@pytest.mark.unit
def test_persona_pool_is_deterministic():
    first = intent._build_personas("DE")
    second = intent._build_personas("DE")
    assert [p.id for p in first] == [p.id for p in second]
    assert [p.search_params for p in first] == [p.search_params for p in second]
    assert [p.entry_point for p in first] == [p.entry_point for p in second]


@pytest.mark.unit
def test_search_params_are_coherent():
    market_makes = set(intent._MARKET["DE"]["models"])
    for persona in intent.PERSONAS["DE"]:
        sp = persona.search_params
        assert sp["make"] in market_makes
        assert sp["year_min"] in intent._YEAR_MINS
        assert sp["budget"] in intent._BUDGETS
        if "model" in sp:
            assert sp["model"] in intent._MARKET["DE"]["models"][sp["make"]]
        if "fuel" in sp:
            assert sp["fuel"] in intent._FUELS


@pytest.mark.unit
def test_pick_persona_returns_from_pool():
    persona = intent.pick_persona("ES", random.Random(0))
    assert persona in intent.PERSONAS["ES"]


@pytest.mark.unit
def test_pick_persona_unknown_country_raises():
    with pytest.raises(ValueError):
        intent.pick_persona("IT")


@pytest.mark.unit
def test_build_plan_flow_and_extract_marker():
    persona = BuyerPersona(
        id="DE-x", country="DE",
        search_params={"make": "BMW", "model": "3er"},
        entry_point="google_search",
    )
    plan = intent.build_plan(persona, "www.autoscout24.de", random.Random(1))

    # ENTRY → homepage
    assert plan.steps[0].action == "navigate"
    assert plan.steps[0].url == "https://www.autoscout24.de/"
    # LANDING scroll, then SEARCH navigate with url left to the executor
    assert plan.steps[1].action == "scroll"
    assert plan.steps[2].action == "navigate"
    assert plan.steps[2].url is None
    # extraction begins at the first BROWSE step
    assert plan.extract_after_step == 3
    assert len(plan.steps) > plan.extract_after_step
    # EXIT → leaves the portal to a Google domain
    assert plan.steps[-1].action == "navigate"
    assert plan.steps[-1].url == "https://www.google.de/"


@pytest.mark.unit
def test_build_plan_google_persona_carries_referer():
    persona = BuyerPersona(
        id="FR-x", country="FR",
        search_params={"make": "Renault", "model": "Clio"},
        entry_point="google_search",
    )
    plan = intent.build_plan(persona, "www.autoscout24.fr", random.Random(2))
    assert plan.steps[0].referer is not None
    assert plan.steps[0].referer.startswith("https://www.google.fr/search?q=")
    assert "Renault" in plan.steps[0].referer


@pytest.mark.unit
def test_build_plan_direct_persona_has_no_referer():
    persona = BuyerPersona(
        id="DE-d", country="DE",
        search_params={"make": "Audi"},
        entry_point="direct",
    )
    plan = intent.build_plan(persona, "www.autoscout24.de", random.Random(3))
    assert plan.steps[0].referer is None


@pytest.mark.unit
def test_browse_navigation_urls_are_not_fabricated():
    persona = BuyerPersona(
        id="DE-b", country="DE", search_params={"make": "Opel"}, entry_point="direct",
    )
    plan = intent.build_plan(persona, "www.autoscout24.de", random.Random(4))
    # Every BROWSE navigate (between extract marker and the final EXIT) is url=None.
    browse = plan.steps[plan.extract_after_step:-1]
    for step in browse:
        if step.action == "navigate":
            assert step.url is None


# ── warming.py — schedule bookkeeping ─────────────────────────────────────────


def _save_identity(conn, make_identity):
    idy = make_identity()
    store.save(conn, idy)
    return idy


@pytest.mark.unit
def test_ensure_phase_row_is_idempotent(conn, make_identity):
    idy = _save_identity(conn, make_identity)
    warming._ensure_phase_row(conn, idy.id, "autoscout24.de", warming.PHASE_PORTAL, 5)
    warming._ensure_phase_row(conn, idy.id, "autoscout24.de", warming.PHASE_PORTAL, 5)
    rows = conn.execute(
        "SELECT requests_done, requests_target FROM warming_schedule "
        "WHERE identity_id=? AND target_domain=? AND phase=?",
        (idy.id, "autoscout24.de", warming.PHASE_PORTAL),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["requests_done"] == 0
    assert rows[0]["requests_target"] == 5


@pytest.mark.unit
def test_record_progress_increments(conn, make_identity):
    idy = _save_identity(conn, make_identity)
    warming._ensure_phase_row(conn, idy.id, "autoscout24.de", warming.PHASE_PORTAL, 5)
    warming._record_progress(conn, idy.id, "autoscout24.de", warming.PHASE_PORTAL)
    warming._record_progress(conn, idy.id, "autoscout24.de", warming.PHASE_PORTAL)
    row = warming._phase_row(conn, idy.id, "autoscout24.de", warming.PHASE_PORTAL)
    assert row["requests_done"] == 2
    assert row["completed_at"] is None
    assert not warming.is_phase_complete(conn, idy.id, "autoscout24.de", warming.PHASE_PORTAL)


@pytest.mark.unit
def test_record_progress_autocompletes_at_target(conn, make_identity):
    idy = _save_identity(conn, make_identity)
    warming._ensure_phase_row(conn, idy.id, "autoscout24.de", warming.PHASE_PORTAL, 2)
    warming._record_progress(conn, idy.id, "autoscout24.de", warming.PHASE_PORTAL)
    assert not warming.is_phase_complete(conn, idy.id, "autoscout24.de", warming.PHASE_PORTAL)
    warming._record_progress(conn, idy.id, "autoscout24.de", warming.PHASE_PORTAL)
    assert warming.is_phase_complete(conn, idy.id, "autoscout24.de", warming.PHASE_PORTAL)


@pytest.mark.unit
def test_complete_phase_sets_timestamp_once(conn, make_identity):
    idy = _save_identity(conn, make_identity)
    warming._ensure_phase_row(conn, idy.id, "autoscout24.de", warming.PHASE_AMBIENT, 50)
    warming._complete_phase(conn, idy.id, "autoscout24.de", warming.PHASE_AMBIENT)
    row = warming._phase_row(conn, idy.id, "autoscout24.de", warming.PHASE_AMBIENT)
    first = row["completed_at"]
    assert first is not None
    # Re-completing must not overwrite the original timestamp (WHERE completed_at IS NULL).
    warming._complete_phase(conn, idy.id, "autoscout24.de", warming.PHASE_AMBIENT)
    row2 = warming._phase_row(conn, idy.id, "autoscout24.de", warming.PHASE_AMBIENT)
    assert row2["completed_at"] == first


@pytest.mark.unit
def test_is_warming_complete_requires_portal_phase(conn, make_identity):
    idy = _save_identity(conn, make_identity)
    # Ambient (phase 1) complete is NOT enough — warming_complete tracks phase 2.
    warming._ensure_phase_row(conn, idy.id, warming._AMBIENT_DOMAIN, warming.PHASE_AMBIENT, 1)
    warming._complete_phase(conn, idy.id, warming._AMBIENT_DOMAIN, warming.PHASE_AMBIENT)
    assert not warming.is_warming_complete(conn, idy.id, "autoscout24.de")

    warming._ensure_phase_row(conn, idy.id, "autoscout24.de", warming.PHASE_PORTAL, 1)
    warming._complete_phase(conn, idy.id, "autoscout24.de", warming.PHASE_PORTAL)
    assert warming.is_warming_complete(conn, idy.id, "autoscout24.de")


@pytest.mark.unit
def test_is_phase_complete_unknown_row_is_false(conn, make_identity):
    idy = _save_identity(conn, make_identity)
    assert not warming.is_phase_complete(conn, idy.id, "nope.de", warming.PHASE_PORTAL)


@pytest.mark.unit
def test_enforce_no_extraction_before_warming_raises(make_identity):
    idy = make_identity()
    assert idy.warming_done is False
    with pytest.raises(RuntimeError):
        warming.enforce_no_extraction_before_warming(idy, "autoscout24.de")


@pytest.mark.unit
def test_enforce_no_extraction_passes_when_warmed(make_identity):
    idy = dataclasses.replace(make_identity(), warming_done=True)
    # Must not raise.
    warming.enforce_no_extraction_before_warming(idy, "autoscout24.de")


# ── state.py — storageState persistence ───────────────────────────────────────


@pytest.mark.unit
def test_load_first_visit_returns_none(conn, make_identity):
    idy = _save_identity(conn, make_identity)
    assert state.load(conn, idy.id, "autoscout24.de") is None


@pytest.mark.unit
def test_save_then_load_roundtrip(conn, make_identity):
    idy = _save_identity(conn, make_identity)
    ss = {"cookies": [{"name": "sid", "value": "abc", "domain": ".autoscout24.de"}], "origins": []}
    state.save(conn, idy.id, "autoscout24.de", ss)
    assert state.load(conn, idy.id, "autoscout24.de") == ss


@pytest.mark.unit
def test_save_isolates_domains(conn, make_identity):
    idy = _save_identity(conn, make_identity)
    a = {"cookies": [{"name": "a", "value": "1"}], "origins": []}
    b = {"cookies": [{"name": "b", "value": "2"}], "origins": []}
    state.save(conn, idy.id, "autoscout24.de", a)
    state.save(conn, idy.id, "mobile.de", b)
    assert state.load(conn, idy.id, "autoscout24.de") == a
    assert state.load(conn, idy.id, "mobile.de") == b


@pytest.mark.unit
def test_save_overwrites_same_domain(conn, make_identity):
    idy = _save_identity(conn, make_identity)
    state.save(conn, idy.id, "autoscout24.de", {"cookies": [], "origins": []})
    new = {"cookies": [{"name": "x", "value": "y"}], "origins": []}
    state.save(conn, idy.id, "autoscout24.de", new)
    assert state.load(conn, idy.id, "autoscout24.de") == new


@pytest.mark.unit
def test_extract_abck_matches_domain():
    ss = {"cookies": [
        {"name": "other", "value": "z", "domain": ".autoscout24.de"},
        {"name": "_abck", "value": "TOKEN123", "domain": ".autoscout24.de"},
    ]}
    assert state.extract_abck(ss, "autoscout24.de") == "TOKEN123"


@pytest.mark.unit
def test_extract_abck_domain_mismatch_returns_none():
    ss = {"cookies": [{"name": "_abck", "value": "T", "domain": ".autoscout24.de"}]}
    assert state.extract_abck(ss, "mobile.de") is None


@pytest.mark.unit
def test_extract_abck_absent_returns_none():
    ss = {"cookies": [{"name": "sid", "value": "T", "domain": ".autoscout24.de"}]}
    assert state.extract_abck(ss, "autoscout24.de") is None


class _FakeContext:
    """Records add_cookies / add_init_script calls from inject_into_context."""

    def __init__(self) -> None:
        self.cookies = None
        self.scripts: list[str] = []

    async def add_cookies(self, cookies):
        self.cookies = cookies

    async def add_init_script(self, script):
        self.scripts.append(script)


@pytest.mark.unit
def test_inject_into_context_applies_cookies_and_localstorage():
    cookies = [{"name": "_abck", "value": "T", "domain": ".autoscout24.de"}]
    ss = {
        "cookies": cookies,
        "origins": [{
            "origin": "https://www.autoscout24.de",
            "localStorage": [{"name": "k", "value": "v"}],
        }],
    }
    ctx = _FakeContext()
    asyncio.run(state.inject_into_context(ctx, ss))
    assert ctx.cookies == cookies
    assert len(ctx.scripts) == 1
    assert "https://www.autoscout24.de" in ctx.scripts[0]


@pytest.mark.unit
def test_inject_into_context_skips_empty():
    ctx = _FakeContext()
    asyncio.run(state.inject_into_context(ctx, {"cookies": [], "origins": []}))
    assert ctx.cookies is None
    assert ctx.scripts == []


@pytest.mark.unit
def test_inject_into_context_skips_origin_without_localstorage():
    ss = {"cookies": [], "origins": [{"origin": "https://www.autoscout24.de", "localStorage": []}]}
    ctx = _FakeContext()
    asyncio.run(state.inject_into_context(ctx, ss))
    assert ctx.scripts == []


# ── conditioning.py — homepage warming flow ───────────────────────────────────


class _FakePage:
    """Minimal page double recording the single goto() conditioning performs."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.goto_args: dict | None = None

    async def goto(self, url, referer=None, wait_until=None, timeout=None):
        self.goto_args = {"url": url, "referer": referer}
        if self.fail:
            raise RuntimeError("navigation blocked")


@pytest.fixture
def _instant_behavioral(monkeypatch):
    """Replace behavioral dwell/reading with counting async no-ops."""
    calls = {"dwell": 0, "reading": 0}

    async def fake_dwell(min_s, max_s):
        calls["dwell"] += 1

    async def fake_reading(page, dwell_s, rng=None):
        calls["reading"] += 1

    monkeypatch.setattr(conditioning.behavioral, "human_dwell", fake_dwell)
    monkeypatch.setattr(conditioning.behavioral, "simulate_reading", fake_reading)
    return calls


@pytest.mark.unit
def test_condition_session_happy_path(_instant_behavioral):
    persona = BuyerPersona(
        id="DE-c", country="DE",
        search_params={"make": "BMW", "model": "3er"},
        entry_point="google_search",
    )
    page = _FakePage()
    asyncio.run(conditioning.condition_session(
        page, "www.autoscout24.de", persona, "https://www.autoscout24.de/",
    ))
    assert page.goto_args["url"] == "https://www.autoscout24.de/"
    assert page.goto_args["referer"].startswith("https://www.google.de/search?q=")
    assert _instant_behavioral["dwell"] == 1
    assert _instant_behavioral["reading"] == 1


@pytest.mark.unit
def test_condition_session_direct_persona_no_referer(_instant_behavioral):
    persona = BuyerPersona(
        id="DE-c2", country="DE", search_params={"make": "Opel"}, entry_point="direct",
    )
    page = _FakePage()
    asyncio.run(conditioning.condition_session(
        page, "www.autoscout24.de", persona, "https://www.autoscout24.de/",
    ))
    assert page.goto_args["referer"] is None
    assert _instant_behavioral["dwell"] == 1


@pytest.mark.unit
def test_condition_session_nav_failure_aborts_cleanly(_instant_behavioral):
    persona = BuyerPersona(
        id="DE-c3", country="DE", search_params={"make": "Ford"}, entry_point="google_search",
    )
    page = _FakePage(fail=True)
    # Must swallow the navigation error and skip the behavioral phase entirely.
    asyncio.run(conditioning.condition_session(
        page, "www.autoscout24.de", persona, "https://www.autoscout24.de/",
    ))
    assert page.goto_args is not None  # goto was attempted
    assert _instant_behavioral["dwell"] == 0
    assert _instant_behavioral["reading"] == 0
