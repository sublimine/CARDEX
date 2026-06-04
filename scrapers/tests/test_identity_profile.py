"""Identity profile generator — coherence-by-construction + determinism."""
from __future__ import annotations

import pytest

from scrapers.engine.identity import coherence, profile
from scrapers.engine.identity.profile import (
    COUNTRY_LOCALES,
    COUNTRY_TIMEZONES,
    ProxyTier,
)

_COUNTRIES = list(COUNTRY_TIMEZONES)


@pytest.mark.unit
@pytest.mark.parametrize("country", _COUNTRIES)
def test_generated_identity_is_coherent(country):
    idy = profile.generate(country, "203.0.113.10", ProxyTier.ISP_STICKY)
    coherence.validate_creation(idy)  # must not raise for any supported country


@pytest.mark.unit
@pytest.mark.parametrize("country", _COUNTRIES)
def test_country_layers_match(country):
    idy = profile.generate(country, "203.0.113.10", ProxyTier.MOBILE)
    assert idy.fingerprint.timezone == COUNTRY_TIMEZONES[country]
    assert idy.fingerprint.locale == COUNTRY_LOCALES[country]


@pytest.mark.unit
def test_webrtc_ip_pinned_to_proxy():
    idy = profile.generate("FR", "198.51.100.42", ProxyTier.RESIDENTIAL_ROTATING)
    assert idy.fingerprint.webrtc_ip == "198.51.100.42"
    assert idy.proxy_ip == "198.51.100.42"


@pytest.mark.unit
def test_same_id_yields_identical_hardware_noise():
    iid = "33333333-3333-3333-3333-333333333333"
    a = profile.generate("DE", "203.0.113.1", ProxyTier.ISP_STICKY, identity_id=iid)
    b = profile.generate("DE", "203.0.113.1", ProxyTier.ISP_STICKY, identity_id=iid)
    assert a.fingerprint.canvas_noise == b.fingerprint.canvas_noise
    assert a.fingerprint.audio_noise == b.fingerprint.audio_noise
    assert a.fingerprint.user_agent == b.fingerprint.user_agent
    assert a.tcp_profile == b.tcp_profile and a.tls_profile == b.tls_profile


@pytest.mark.unit
def test_unsupported_country_rejected():
    with pytest.raises(ValueError):
        profile.generate("US", "203.0.113.1", ProxyTier.ISP_STICKY)


@pytest.mark.unit
def test_archetype_os_browser_never_crossed():
    # Sweep many ids; every fingerprint must remain a single coherent archetype.
    for n in range(50):
        iid = f"00000000-0000-0000-0000-{n:012d}"
        idy = profile.generate("NL", "203.0.113.5", ProxyTier.ISP_STICKY, identity_id=iid)
        coherence.validate_creation(idy)
