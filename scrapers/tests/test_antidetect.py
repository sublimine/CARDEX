"""Antidetect block — tcp profile, behavioral motion, Camoufox pool, Akamai sensor."""
from __future__ import annotations

import asyncio
import time

import pytest

from scrapers.engine.antidetect import behavioral, browser, sensor, tcp
from scrapers.engine.antidetect.browser import BrowserSlot, CamoufoxPool, proxy_dict_from_url
from scrapers.engine.identity import store
from scrapers.engine.identity.profile import TCPProfile


# --------------------------------------------------------------------------- #
# helpers — fake async page/context + instant sleep
# --------------------------------------------------------------------------- #
async def _instant(*_a, **_k) -> None:
    return None


class _FakeMouse:
    def __init__(self) -> None:
        self.moves: list[tuple[float, float]] = []
        self.wheels: list[tuple[int, int]] = []

    async def move(self, x: float, y: float) -> None:
        self.moves.append((x, y))

    async def wheel(self, dx: int, dy: int) -> None:
        self.wheels.append((dx, dy))


class _FakeElement:
    def __init__(self, box: dict | None) -> None:
        self._box = box

    async def bounding_box(self) -> dict | None:
        return self._box


class _FakePage:
    def __init__(self, element: _FakeElement | None = None) -> None:
        self.mouse = _FakeMouse()
        self._element = element

    async def query_selector(self, _selector: str):
        return self._element


# --------------------------------------------------------------------------- #
# tcp — availability detection + degraded apply_profile
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_is_available_true_when_binary_and_pcap_present(monkeypatch):
    monkeypatch.setattr(tcp.shutil, "which", lambda _b: "/usr/bin/httpcloak")
    monkeypatch.setattr(tcp, "_pcap_present", lambda: True)
    assert tcp.is_available() is True


@pytest.mark.unit
def test_is_available_false_when_binary_missing(monkeypatch):
    monkeypatch.setattr(tcp.shutil, "which", lambda _b: None)
    monkeypatch.setattr(tcp, "_pcap_present", lambda: True)
    assert tcp.is_available() is False


@pytest.mark.unit
def test_is_available_false_when_pcap_missing(monkeypatch):
    monkeypatch.setattr(tcp.shutil, "which", lambda _b: "/usr/bin/httpcloak")
    monkeypatch.setattr(tcp, "_pcap_present", lambda: False)
    assert tcp.is_available() is False


@pytest.mark.unit
def test_profiles_cover_every_tcp_profile_enum():
    # apply_profile indexes _PROFILES[identity.tcp_profile] unconditionally, so a
    # missing enum member would KeyError in production. Guard it here.
    for member in TCPProfile:
        assert member in tcp._PROFILES
        assert {"ttl", "window", "options"} <= tcp._PROFILES[member].keys()


@pytest.mark.unit
def test_apply_profile_degraded_warns_once(monkeypatch, make_identity, caplog):
    monkeypatch.setattr(tcp, "is_available", lambda: False)
    monkeypatch.setattr(tcp, "_degraded_warned", False)
    idy = make_identity()
    with caplog.at_level("WARNING"):
        tcp.apply_profile(idy)
        tcp.apply_profile(idy)  # second call must not re-warn
    degraded = [r for r in caplog.records if "degraded mode" in r.message]
    assert len(degraded) == 1


@pytest.mark.unit
def test_apply_profile_available_is_noop_without_raise(monkeypatch, make_identity):
    monkeypatch.setattr(tcp, "is_available", lambda: True)
    tcp.apply_profile(make_identity())  # must not raise


# --------------------------------------------------------------------------- #
# behavioral — pure geometry helpers
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_bezier_endpoints_are_exact():
    import random

    pts = behavioral._bezier_points((0.0, 0.0), (100.0, 50.0), steps=20, jitter=40, rng=random.Random(7))
    assert len(pts) == 21
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (100.0, 50.0)


@pytest.mark.unit
def test_bezier_path_is_curved_not_straight():
    import random

    start, end, steps = (0.0, 0.0), (100.0, 100.0), 20
    pts = behavioral._bezier_points(start, end, steps=steps, jitter=40, rng=random.Random(3))
    # Max perpendicular deviation from the straight diagonal must be non-trivial.
    max_dev = 0.0
    for i, (x, y) in enumerate(pts):
        t = i / steps
        lin_x, lin_y = start[0] + t * (end[0] - start[0]), start[1] + t * (end[1] - start[1])
        max_dev = max(max_dev, abs(x - lin_x) + abs(y - lin_y))
    assert max_dev > 1.0


@pytest.mark.unit
def test_scroll_steps_positive_sum_and_length():
    import random

    steps = behavioral._scroll_steps(1000, variance=0.0, rng=random.Random(1), n=5)
    assert len(steps) == 5
    assert all(s > 0 for s in steps)
    assert abs(sum(steps) - 1000) <= 5  # only per-chunk int truncation


@pytest.mark.unit
def test_scroll_steps_preserves_negative_direction():
    import random

    steps = behavioral._scroll_steps(-1000, variance=0.0, rng=random.Random(1), n=5)
    assert all(s < 0 for s in steps)
    assert abs(sum(steps) + 1000) <= 5


@pytest.mark.unit
def test_scroll_steps_clamps_to_minimum_one():
    import random

    steps = behavioral._scroll_steps(3, variance=0.0, rng=random.Random(1), n=8)
    assert len(steps) == 8
    assert all(s >= 1 for s in steps)  # max(1, chunk) prevents zero-size scrolls


@pytest.mark.unit
def test_human_scroll_emits_wheel_events(monkeypatch):
    import random

    monkeypatch.setattr(asyncio, "sleep", _instant)
    page = _FakePage()
    asyncio.run(behavioral.human_scroll(page, 800, rng=random.Random(2)))
    assert len(page.mouse.wheels) >= 4
    assert all(dy > 0 for _dx, dy in page.mouse.wheels)


@pytest.mark.unit
def test_move_to_element_lands_inside_box(monkeypatch):
    import random

    monkeypatch.setattr(asyncio, "sleep", _instant)
    box = {"x": 100.0, "y": 200.0, "width": 50.0, "height": 20.0}
    page = _FakePage(_FakeElement(box))
    asyncio.run(behavioral.move_to_element(page, "button", rng=random.Random(5)))
    assert page.mouse.moves
    final_x, final_y = page.mouse.moves[-1]
    assert box["x"] <= final_x <= box["x"] + box["width"]
    assert box["y"] <= final_y <= box["y"] + box["height"]


@pytest.mark.unit
def test_move_to_element_missing_element_is_noop(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _instant)
    page = _FakePage(element=None)
    asyncio.run(behavioral.move_to_element(page, "missing"))
    assert page.mouse.moves == []


@pytest.mark.unit
def test_simulate_reading_scrolls_within_budget(monkeypatch):
    import random

    monkeypatch.setattr(asyncio, "sleep", _instant)
    page = _FakePage()
    asyncio.run(behavioral.simulate_reading(page, (1.0, 1.0), rng=random.Random(4)))
    assert page.mouse.wheels  # at least one reading scroll happened


# --------------------------------------------------------------------------- #
# browser — proxy_dict_from_url
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_proxy_dict_none_for_empty():
    assert proxy_dict_from_url(None) is None
    assert proxy_dict_from_url("") is None


@pytest.mark.unit
def test_proxy_dict_full_credentials():
    out = proxy_dict_from_url("http://user:pass@host.example:8080")
    assert out == {"server": "http://host.example:8080", "username": "user", "password": "pass"}


@pytest.mark.unit
def test_proxy_dict_without_credentials():
    out = proxy_dict_from_url("http://host.example:3128")
    assert out == {"server": "http://host.example:3128"}


@pytest.mark.unit
def test_proxy_dict_defaults_scheme_and_omits_port():
    out = proxy_dict_from_url("host.only")
    # No scheme → urlparse puts "host.only" in path, hostname is None → unparseable.
    assert out is None


@pytest.mark.unit
def test_proxy_dict_preserves_https_scheme():
    out = proxy_dict_from_url("https://u:p@h:9000")
    assert out["server"] == "https://h:9000"


# --------------------------------------------------------------------------- #
# browser — CamoufoxPool acquire/reuse/eviction/close (monkeypatched launch)
# --------------------------------------------------------------------------- #
def _instrument_pool(pool: CamoufoxPool, counters: dict) -> None:
    async def fake_launch(identity, domain):
        counters["launched"] += 1
        return BrowserSlot(
            identity=identity, browser=object(), page=object(),
            domain=domain, in_use=True, cm=object(),
        )

    async def fake_shutdown(slot):
        counters["shutdown"] += 1

    pool._launch = fake_launch
    pool._shutdown = fake_shutdown


@pytest.mark.unit
def test_pool_acquire_launches_once_and_reuses(make_identity):
    counters = {"launched": 0, "shutdown": 0}
    pool = CamoufoxPool(pool_size=2)
    _instrument_pool(pool, counters)
    idy = make_identity()

    async def scenario():
        slot = await pool.acquire(idy, "autoscout24.de")
        assert slot.in_use is True
        await pool.release(slot)
        slot2 = await pool.acquire(idy, "autoscout24.de")  # idle same-identity reuse
        assert slot2 is slot

    asyncio.run(scenario())
    assert counters["launched"] == 1  # second acquire reused, no relaunch


@pytest.mark.unit
def test_pool_evicts_idle_other_identity_when_full(make_identity):
    counters = {"launched": 0, "shutdown": 0}
    pool = CamoufoxPool(pool_size=1)
    _instrument_pool(pool, counters)
    a = make_identity(identity_id="11111111-1111-1111-1111-111111111111")
    b = make_identity(identity_id="22222222-2222-2222-2222-222222222222")

    async def scenario():
        slot_a = await pool.acquire(a, "d.com")
        await pool.release(slot_a)              # A now idle
        slot_b = await pool.acquire(b, "d.com")  # full → must evict idle A, launch B
        assert slot_b.identity.id == b.id

    asyncio.run(scenario())
    assert counters["launched"] == 2
    assert counters["shutdown"] == 1  # A was evicted


@pytest.mark.unit
def test_pool_close_all_shuts_every_slot(make_identity):
    counters = {"launched": 0, "shutdown": 0}
    pool = CamoufoxPool(pool_size=4)
    _instrument_pool(pool, counters)

    async def scenario():
        s1 = await pool.acquire(make_identity(identity_id="11111111-1111-1111-1111-111111111111"), "d.com")
        s2 = await pool.acquire(make_identity(identity_id="22222222-2222-2222-2222-222222222222"), "d.com")
        await pool.release(s1)
        await pool.release(s2)
        await pool.close_all()

    asyncio.run(scenario())
    assert counters["shutdown"] == 2


# --------------------------------------------------------------------------- #
# sensor — _abck token store/expiry/refresh
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_store_and_get_token_roundtrip(conn, make_identity):
    idy = make_identity()
    store.save(conn, idy)
    sensor.store_token(conn, idy.id, "autoscout24.de", "TOKEN", int(time.time()) + 3600)
    got = sensor.get_token(conn, idy.id, "autoscout24.de")
    assert got is not None
    assert got["token"] == "TOKEN"
    assert got["request_count"] == 0


@pytest.mark.unit
def test_get_token_expired_returns_none(conn, make_identity):
    idy = make_identity()
    store.save(conn, idy)
    sensor.store_token(conn, idy.id, "autoscout24.de", "OLD", int(time.time()) - 5)
    assert sensor.get_token(conn, idy.id, "autoscout24.de") is None


@pytest.mark.unit
def test_get_token_unknown_identity_or_domain(conn, make_identity):
    idy = make_identity()
    store.save(conn, idy)
    assert sensor.get_token(conn, "nonexistent-id", "autoscout24.de") is None
    assert sensor.get_token(conn, idy.id, "never-visited.de") is None


@pytest.mark.unit
def test_store_token_unknown_identity_is_noop(conn):
    sensor.store_token(conn, "ghost-id", "autoscout24.de", "T", int(time.time()) + 3600)
    assert sensor.get_token(conn, "ghost-id", "autoscout24.de") is None


@pytest.mark.unit
def test_needs_refresh_thresholds():
    fresh = {"expires": int(time.time()) + 7200, "request_count": 10}
    assert sensor.needs_refresh(fresh) is False
    expiring = {"expires": int(time.time()) + 1000, "request_count": 10}
    assert sensor.needs_refresh(expiring) is True
    overused = {"expires": int(time.time()) + 7200, "request_count": 501}
    assert sensor.needs_refresh(overused) is True


@pytest.mark.unit
def test_hyper_sdk_path_reflects_which(monkeypatch):
    monkeypatch.setattr(sensor.shutil, "which", lambda _b: "/opt/hyper-sdk-go")
    assert sensor.hyper_sdk_path() == "/opt/hyper-sdk-go"
    monkeypatch.setattr(sensor.shutil, "which", lambda _b: None)
    assert sensor.hyper_sdk_path() is None


@pytest.mark.unit
def test_refresh_token_degraded_returns_none(monkeypatch):
    monkeypatch.setattr(sensor, "hyper_sdk_path", lambda: None)
    out = asyncio.run(sensor.refresh_token("id", "autoscout24.de", "http://proxy:8080"))
    assert out is None
    monkeypatch.setattr(sensor, "hyper_sdk_path", lambda: "/opt/hyper-sdk-go")
    out2 = asyncio.run(sensor.refresh_token("id", "autoscout24.de", "http://proxy:8080"))
    assert out2 is None  # present-but-unconfigured still degrades to Fase 2
