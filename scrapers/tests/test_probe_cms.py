"""
Inventory probe × cms_fingerprint seam — the at-scale probe enriches the
``inventory_signals`` jsonb with the platform-family verdict (``cms`` /
``cms_confidence`` / ``cms_signals``) fingerprinted from the SAME homepage body
it already fetched (zero extra I/O). Everything runs against in-memory
aiohttp/asyncpg fakes — no network, no DB — and the legacy jsonb contract is
asserted byte-for-byte unchanged (no-regression).
"""
from __future__ import annotations

import asyncio
import json

from scrapers.dealer_scraping import inventory_probe as ip


# ── in-memory transport / DB fakes ──────────────────────────────────────────────
class _FakeContent:
    def __init__(self, body: bytes):
        self._body = body

    async def iter_chunked(self, size: int):
        for i in range(0, len(self._body), size):
            yield self._body[i:i + size]


class FakeResponse:
    def __init__(self, status: int = 200, url: str = "", headers: dict | None = None,
                 body: bytes = b""):
        self.status = status
        self.url = url
        self.headers = headers or {}
        self.content = _FakeContent(body)


class FakeSession:
    """HEAD answers alive on https, GET serves the canned homepage, sitemap 404s."""

    def __init__(self, home_html: str, headers: dict | None = None):
        self._home = home_html.encode("utf-8")
        self._headers = headers or {}

    async def head(self, url: str, **kwargs) -> FakeResponse:
        return FakeResponse(status=200, url=url, headers=self._headers)

    async def get(self, url: str, **kwargs) -> FakeResponse:
        if url.endswith("/sitemap.xml"):
            return FakeResponse(status=404, url=url)
        return FakeResponse(status=200, url=url, headers=self._headers, body=self._home)


class FakeConn:
    def __init__(self):
        self.calls: list[tuple[str, list]] = []

    async def executemany(self, sql: str, payload) -> None:
        self.calls.append((sql, list(payload)))


class FakePool:
    def __init__(self, conn: FakeConn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Ctx()


def _probe_and_store(monkeypatch, home_html: str):
    """Probe one fake dealer end-to-end and capture the jsonb write_results emits."""
    monkeypatch.setattr(ip, "is_safe_public_url", lambda url, resolve=True: True)
    result = asyncio.run(ip.probe(FakeSession(home_html), "dealer.example", "DE", timeout=5))
    conn = FakeConn()
    asyncio.run(ip.write_results(FakePool(conn), [result]))
    ((_sql, rows),) = conn.calls
    (row,) = rows
    return result, json.loads(row[1]), row


# ── fixtures ─────────────────────────────────────────────────────────────────────
# WordPress home: two distinct family markers (wp-content + wp-json) plus the
# legacy inventory signals (vehicle URL pattern + count text) so the pre-existing
# probe behaviour is exercised alongside the new cms seam.
_WORDPRESS_HOME = (
    "<html><head>"
    '<link rel="stylesheet" href="/wp-content/themes/dealer/style.css">'
    '<link rel="https://api.w.org/" href="/wp-json/">'
    "</head><body>"
    '<a href="/fahrzeuge">12 Fahrzeuge auf Lager</a>'
    "</body></html>"
)

# Bare brochure home: no platform marker, no inventory signal, not parked.
_BARE_HOME = (
    "<html><head><title>Garage Muster</title></head>"
    "<body><p>Willkommen in unserer Werkstatt.</p></body></html>"
)

_LEGACY_KEYS = ("signals", "waf", "http_status", "vehicle_count_est", "parked",
                "final_url", "probe_ms", "error")


# ── tests ─────────────────────────────────────────────────────────────────────────
def test_known_family_home_enriches_signals_with_cms_verdict(monkeypatch):
    # Arrange / Act
    result, stored, _row = _probe_and_store(monkeypatch, _WORDPRESS_HOME)

    # Assert — the verdict rides along in the jsonb, coherent across the 3 keys
    assert stored["cms"] == "wordpress"
    assert stored["cms_signals"] == ["wp-content", "wp-json"]
    assert stored["cms_confidence"] == "high"          # >=2 distinct signals fired
    assert result.cms == "wordpress"                    # mirrored on the ProbeResult


def test_no_marker_home_writes_empty_cms_without_breaking_dict(monkeypatch):
    # Arrange / Act
    _result, stored, row = _probe_and_store(monkeypatch, _BARE_HOME)

    # Assert — cms is "" (not "unknown") and the rest of the dict is intact
    assert stored["cms"] == ""
    assert stored["cms_confidence"] == "unknown"
    assert stored["cms_signals"] == []
    assert stored["http_status"] == 200
    assert stored["signals"] == []
    assert stored["parked"] is False
    assert stored["error"] is None
    assert row[0] == "T3"        # tier classification untouched by the cms seam
    assert row[2] == "none"      # sitemap_status mapping untouched


def test_legacy_jsonb_contract_unchanged(monkeypatch):
    # Arrange / Act
    result, stored, row = _probe_and_store(monkeypatch, _WORDPRESS_HOME)

    # Assert — every key the probe already wrote is present and equal
    expected_legacy = {
        "signals": result.signals, "waf": result.waf, "http_status": result.http_status,
        "vehicle_count_est": result.vehicle_count_est, "parked": result.parked,
        "final_url": result.final_url, "probe_ms": result.probe_ms, "error": result.error,
    }
    assert {k: stored[k] for k in _LEGACY_KEYS} == expected_legacy
    # exactly the three additive keys on top of the legacy contract — nothing else
    assert set(stored) == set(_LEGACY_KEYS) | {"cms", "cms_confidence", "cms_signals"}
    # legacy probe behaviour still observed end-to-end on the same fetch
    assert result.signals == ["url_pattern", "count_text:12"]
    assert result.vehicle_count_est == 12
    assert (row[0], row[2]) == ("T2", "found")          # tier + status mapping intact
    assert (row[3], row[4]) == ("dealer.example", "DE")  # WHERE-clause params intact


# == DEAD-confirmation pass (anti false-DEAD, 2026-06-10) =========================
class _FlakySession:
    """Fails every request on the FIRST pass, answers normally afterwards -
    models the transient local-network saturation that minted false DEADs."""

    def __init__(self, fail_first_n: int = 2):
        self.calls = 0
        self.fail_first_n = fail_first_n

    async def head(self, url: str, **kwargs) -> FakeResponse:
        self.calls += 1
        if self.calls <= self.fail_first_n:
            raise OSError("simulated saturation")
        return FakeResponse(status=200, url=url)

    async def get(self, url: str, **kwargs) -> FakeResponse:
        if url.endswith("/sitemap.xml"):
            return FakeResponse(status=404, url=url)
        return FakeResponse(status=200, url=url, body=b"<html>plain dealer home</html>")


class _AlwaysDownSession:
    async def head(self, url: str, **kwargs) -> FakeResponse:
        raise OSError("really down")

    async def get(self, url: str, **kwargs) -> FakeResponse:
        raise OSError("really down")


def test_dead_confirmation_revives_transient_failure(monkeypatch):
    # Arrange - both schemes fail on pass 1 (2 head calls), revive on pass 2.
    monkeypatch.setattr(ip, "is_safe_public_url", lambda url, resolve=True: True)
    monkeypatch.setattr(ip, "DEAD_RECHECK_PAUSE_S", 0.0)
    rows = [{"domain": "flaky.nl", "country": "NL"}]

    # Act
    results = asyncio.run(ip.run_probes(_FlakySession(fail_first_n=2), rows,
                                        concurrency=2, timeout=1))

    # Assert - the transient failure never reaches the DEAD verdict.
    assert results[0].alive is True
    assert results[0].tier != "DEAD"


def test_dead_confirmation_keeps_truly_dead(monkeypatch):
    # Arrange
    monkeypatch.setattr(ip, "is_safe_public_url", lambda url, resolve=True: True)
    monkeypatch.setattr(ip, "DEAD_RECHECK_PAUSE_S", 0.0)
    rows = [{"domain": "gone.nl", "country": "NL"}]

    # Act
    results = asyncio.run(ip.run_probes(_AlwaysDownSession(), rows, concurrency=2, timeout=1))

    # Assert - failing BOTH passes is what DEAD means.
    assert results[0].tier == "DEAD"
