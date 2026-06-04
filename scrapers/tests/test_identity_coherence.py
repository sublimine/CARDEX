"""Coherence enforcer — every incoherence must raise CoherenceError."""
from __future__ import annotations

import dataclasses
import json

import pytest

from scrapers.engine.identity import coherence, profile
from scrapers.engine.identity.coherence import CoherenceError, ua_browser, ua_os
from scrapers.engine.identity.profile import ProxyTier

_UA_CHROME_WIN = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
_UA_FIREFOX_WIN = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0"
)
_UA_SAFARI_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/26.0 Safari/605.1.15"
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "ua,expected",
    [
        (_UA_CHROME_WIN, "windows"),
        (_UA_SAFARI_MAC, "macos"),
        ("Mozilla/5.0 (X11; Linux x86_64)", "linux"),
    ],
)
def test_ua_os(ua, expected):
    assert ua_os(ua) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "ua,expected",
    [
        (_UA_CHROME_WIN, "chrome"),
        (_UA_FIREFOX_WIN, "firefox"),
        (_UA_SAFARI_MAC, "safari"),
    ],
)
def test_ua_browser(ua, expected):
    # Order matters: Firefox/Edge must win before the Chrome/Safari tokens.
    assert ua_browser(ua) == expected


@pytest.mark.unit
def test_no_fingerprint_rejected():
    idy = profile.generate("DE", "203.0.113.1", ProxyTier.ISP_STICKY)
    idy = dataclasses.replace(idy, fingerprint=None)
    with pytest.raises(CoherenceError, match="no fingerprint"):
        coherence.validate_creation(idy)


@pytest.mark.unit
def test_webrtc_mismatch_rejected():
    idy = profile.generate("DE", "203.0.113.1", ProxyTier.ISP_STICKY)
    bad = dataclasses.replace(idy, proxy_ip="9.9.9.9")  # webrtc_ip still old
    with pytest.raises(CoherenceError, match="webrtc_ip"):
        coherence.validate_creation(bad)


@pytest.mark.unit
def test_timezone_mismatch_rejected():
    idy = profile.generate("DE", "203.0.113.1", ProxyTier.ISP_STICKY)
    fp = dataclasses.replace(idy.fingerprint, timezone="Europe/Paris")
    bad = dataclasses.replace(idy, fingerprint=fp)
    with pytest.raises(CoherenceError, match="timezone"):
        coherence.validate_creation(bad)


@pytest.mark.unit
def test_pre_session_rejects_corrupt_storage_state():
    idy = profile.generate("DE", "203.0.113.1", ProxyTier.ISP_STICKY)
    bad = dataclasses.replace(idy, storage_state=b"{not valid json")
    with pytest.raises(CoherenceError, match="corrupt"):
        coherence.validate_pre_session(bad, "autoscout24.de")


@pytest.mark.unit
def test_pre_session_accepts_valid_storage_state():
    idy = profile.generate("DE", "203.0.113.1", ProxyTier.ISP_STICKY)
    good = dataclasses.replace(
        idy, storage_state=json.dumps({"cookies": [], "origins": []}).encode()
    )
    coherence.validate_pre_session(good, "autoscout24.de")  # must not raise
