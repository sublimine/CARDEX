"""Tests for S-HOST (host_budget): the global resource broker.

No PG needed: the RAM/disk gates are exercised by monkeypatching the OS readers,
and the cross-process slot is exercised on its process-local fallback path.
"""
import asyncio

import scrapers.common.host_budget as hb


def test_available_mb_is_positive_int():
    # Act
    mb = hb.available_mb()
    # Assert
    assert isinstance(mb, int)
    assert mb > 0


def test_disk_free_gb_is_positive():
    assert hb.disk_free_gb() > 0


def test_ram_state_crosses_thresholds(monkeypatch):
    # Arrange / Act / Assert across the three bands
    monkeypatch.setattr(hb, "available_mb", lambda: hb.RAM_HARD_MB - 1)
    assert hb.ram_state() == "HARD"
    monkeypatch.setattr(hb, "available_mb", lambda: hb.RAM_SOFT_MB - 1)
    assert hb.ram_state() == "SOFT"
    monkeypatch.setattr(hb, "available_mb", lambda: hb.RAM_SOFT_MB + 100)
    assert hb.ram_state() == "OK"


def test_effective_conc_backs_off_under_pressure(monkeypatch):
    monkeypatch.setattr(hb, "available_mb", lambda: hb.RAM_SOFT_MB + 100)  # OK
    assert hb.effective_conc(8) == 8
    monkeypatch.setattr(hb, "available_mb", lambda: hb.RAM_SOFT_MB - 1)    # SOFT
    assert hb.effective_conc(8) == 4
    monkeypatch.setattr(hb, "available_mb", lambda: hb.RAM_HARD_MB - 1)    # HARD
    assert hb.effective_conc(8) == 0


def test_throttle_reason_flags_ram_and_disk(monkeypatch):
    # Healthy: no reason
    monkeypatch.setattr(hb, "available_mb", lambda: hb.RAM_SOFT_MB + 100)
    monkeypatch.setattr(hb, "disk_free_gb", lambda *a, **k: hb.DISK_MIN_GB + 100)
    assert hb.throttle_reason() is None
    # RAM hard pressure
    monkeypatch.setattr(hb, "available_mb", lambda: hb.RAM_HARD_MB - 1)
    assert hb.throttle_reason().startswith("RAM_HARD")
    # Disk low pressure
    monkeypatch.setattr(hb, "available_mb", lambda: hb.RAM_SOFT_MB + 100)
    monkeypatch.setattr(hb, "disk_free_gb", lambda *a, **k: hb.DISK_MIN_GB - 1)
    assert hb.throttle_reason().startswith("DISK_LOW")


def test_slot_local_path_caps_concurrency(monkeypatch):
    # Arrange: force the process-local fallback (pool=None) with a budget of 2.
    monkeypatch.setitem(hb.LANE_BUDGET, "browser", 2)
    hb._LOCAL_SEMS.clear()
    state = {"cur": 0, "max": 0}

    async def worker():
        async with hb.slot(None, "browser"):
            state["cur"] += 1
            state["max"] = max(state["max"], state["cur"])
            await asyncio.sleep(0.05)
            state["cur"] -= 1

    async def main():
        await asyncio.gather(*(worker() for _ in range(6)))

    # Act
    asyncio.run(main())

    # Assert: never more than the budget ran at once.
    assert state["max"] == 2
