"""cdx_code — deterministic immutable entity code (pure tests)."""
from __future__ import annotations

import re

import pytest

from scrapers.intelligence.cdx_code import cdx_code, entity_identity

_FMT = re.compile(r"^CDX-[A-Z]{2}-[A-Z2-7]{8}$")  # base32 alphabet


@pytest.mark.unit
def test_format_and_country_prefix():
    code = cdx_code("FR", domain="www.dacia-meaux.fr")
    assert _FMT.match(code), code
    assert code.startswith("CDX-FR-")


@pytest.mark.unit
def test_deterministic_same_identity_same_code():
    a = cdx_code("FR", domain="https://www.Dacia-Meaux.fr/")
    b = cdx_code("FR", domain="dacia-meaux.fr")          # normalización (proto/www/case/slash)
    assert a == b  # misma entidad física → mismo código siempre (idempotente)


@pytest.mark.unit
def test_different_entities_different_codes():
    a = cdx_code("FR", domain="dacia-meaux.fr")
    b = cdx_code("FR", domain="renault-paris.fr")
    assert a != b


@pytest.mark.unit
def test_identity_priority_domain_over_registry_over_name():
    # dominio gana sobre registro y nombre
    assert entity_identity("FR", domain="x.fr", registry_id="123", name="X").startswith("d:")
    # sin dominio: registro gana sobre nombre
    assert entity_identity("FR", registry_id="812763167", name="X").startswith("r:FR:")
    # sin dominio ni registro: nombre+ciudad
    assert entity_identity("FR", name="Garage Dupont", city="Nimes").startswith("n:FR:")


@pytest.mark.unit
def test_registry_code_stable_and_country_scoped():
    a = cdx_code("FR", registry_id="812763167")
    b = cdx_code("FR", registry_id="812763167")
    assert a == b and a.startswith("CDX-FR-")
    # mismo registro distinto país = entidad distinta (registro es país-scoped en la identidad)
    assert cdx_code("ES", registry_id="812763167") != a


@pytest.mark.unit
def test_no_stable_identity_returns_none():
    assert cdx_code("FR") is None                 # sin nada
    assert cdx_code("FR", name="   ") is None      # nombre vacío


@pytest.mark.unit
def test_name_city_fallback_normalizes():
    a = cdx_code("FR", name="Garage  DUPONT!!", city="Nîmes")
    b = cdx_code("FR", name="garage dupont", city="nîmes")
    assert a == b is not None
