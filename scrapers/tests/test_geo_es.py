"""ES province derivation from postcode — deterministic reference mapping."""
import pytest

from scrapers.discovery.geo_es import ES_PROVINCES, province_from_postcode


@pytest.mark.unit
def test_known_postcodes_map_to_correct_province():
    assert province_from_postcode("17001") == "Girona"      # dificar.com
    assert province_from_postcode("28044") == "Madrid"
    assert province_from_postcode("08380") == "Barcelona"
    assert province_from_postcode("07009") == "Illes Balears"
    assert province_from_postcode("10005") == "Cáceres"


@pytest.mark.unit
def test_leading_zero_postcode_handled():
    assert province_from_postcode("01001") == "Álava"
    assert province_from_postcode("1001") == "Álava"        # missing leading zero


@pytest.mark.unit
def test_undecidable_postcodes_return_none():
    assert province_from_postcode(None) is None
    assert province_from_postcode("") is None
    assert province_from_postcode("7") is None
    assert province_from_postcode("99999") is None          # 99 is not a province


@pytest.mark.unit
def test_all_52_provinces_present():
    assert len(ES_PROVINCES) == 52
    assert ES_PROVINCES["01"] == "Álava" and ES_PROVINCES["52"] == "Melilla"
