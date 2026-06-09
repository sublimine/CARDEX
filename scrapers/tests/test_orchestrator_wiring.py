"""Orchestrator wiring contract — every registered source is importable and shaped right.

Structural only (no network/DB): guards against a source being referenced but missing its
contract method, and against the OEM franchise sweeps silently dropping out of production.
"""
from __future__ import annotations

import asyncio
import importlib
import inspect

import pytest

from scrapers.discovery import orchestrator as orch


@pytest.mark.unit
def test_discover_sources_have_contract():
    # Every (name, factory, gate) in _SOURCES must yield an object exposing discover().
    assert orch._SOURCES, "no discover() sources registered"
    for name, factory, gate in orch._SOURCES:
        src = factory(None)  # client not touched at construction time
        assert hasattr(src, "discover"), f"{name} source lacks discover()"
        assert callable(gate)


@pytest.mark.unit
def test_oem_franchise_sweeps_are_wired_as_standalone():
    # The franchise long-tail must be in the production sweep, not standalone-only scripts.
    for mod in ("oem_locators", "oem_wave2", "oem_brands_ext"):
        assert mod in orch._STANDALONE_RUNNERS, f"{mod} not wired into _STANDALONE_RUNNERS"


@pytest.mark.unit
def test_every_standalone_runner_imports_and_has_async_run():
    for name in orch._STANDALONE_RUNNERS:
        module = importlib.import_module(f"scrapers.discovery.sources.{name}")
        run = getattr(module, "run", None)
        assert run is not None and callable(run), f"{name}.run missing"
        assert asyncio.iscoroutinefunction(run), f"{name}.run is not async"


@pytest.mark.unit
def test_standalone_run_accepts_no_args():
    # _run_standalone calls module.run() with NO args — every runner must default cleanly.
    for name in orch._STANDALONE_RUNNERS:
        module = importlib.import_module(f"scrapers.discovery.sources.{name}")
        sig = inspect.signature(module.run)
        required = [p for p in sig.parameters.values()
                    if p.default is inspect.Parameter.empty
                    and p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY)]
        assert not required, f"{name}.run requires args {required} but is called no-arg"


@pytest.mark.unit
def test_as24_dealers_gate_covers_five_countries_not_ch():
    gate = next(g for n, _, g in orch._SOURCES if n == "as24_dealers")
    assert [gate(c) for c in ("DE", "FR", "ES", "NL", "BE")] == [True] * 5
    assert gate("CH") is False  # autoscout24.ch is a separate platform
