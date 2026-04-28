"""Test fuel and transmission normalizers."""
from scrapers.discovery.meili_enricher import _norm_fuel, _norm_tx


def test_norm_fuel():
    cases = [
        ("Diesel", "DIESEL"),
        ("diesel", "DIESEL"),
        ("Gasoil", "DIESEL"),
        ("Blue HDi", "DIESEL"),
        ("TDI 150", "DIESEL"),
        ("Essence", "GASOLINE"),
        ("gasoline", "GASOLINE"),
        ("Petrol", "GASOLINE"),
        ("Benzin", "GASOLINE"),
        ("TSI 1.4", "GASOLINE"),
        ("Gasolina", "GASOLINE"),
        ("Hybride", "HYBRID"),
        ("Hybrid", "HYBRID"),
        ("Híbrido", "HYBRID"),
        ("Plug-in Hybrid", "PLUG_IN_HYBRID"),
        ("PHEV", "PLUG_IN_HYBRID"),
        ("Mild Hybrid", "MILD_HYBRID"),
        ("MHEV", "MILD_HYBRID"),
        ("Electric", "ELECTRIC"),
        ("Électrique", "ELECTRIC"),
        ("BEV", "ELECTRIC"),
        ("Elettrica", "ELECTRIC"),
        ("LPG", "LPG"),
        ("GPL", "LPG"),
        ("Autogas", "LPG"),
        ("CNG", "CNG"),
        ("Erdgas", "CNG"),
        ("Wasserstoff", "HYDROGEN"),
        ("H2", "HYDROGEN"),
        ("E85", "ETHANOL"),
    ]
    failed = 0
    for raw, expected in cases:
        got = _norm_fuel(raw)
        if got != expected:
            print(f"FAIL _norm_fuel({raw!r}) -> {got}, expected {expected}")
            failed += 1
    assert failed == 0, f"{failed} cases failed"
    print(f"PASS all {len(cases)} fuel normalizations")


def test_norm_tx():
    cases = [
        ("Automatic", "AUTOMATIC"),
        ("Automatik", "AUTOMATIC"),
        ("Automatique", "AUTOMATIC"),
        ("DSG 7", "AUTOMATIC"),
        ("PDK", "AUTOMATIC"),
        ("Tiptronic", "AUTOMATIC"),
        ("S-Tronic", "AUTOMATIC"),
        ("EAT8", "AUTOMATIC"),
        ("DCT", "AUTOMATIC"),
        ("Manual", "MANUAL"),
        ("Manuel", "MANUAL"),
        ("Manuale", "MANUAL"),
        ("Schaltgetriebe", "MANUAL"),
        ("BVM6", "MANUAL"),
        ("CVT", "CVT"),
        ("Stufenlos", "CVT"),
        ("Semi-Automatic", "SEMI_AUTOMATIC"),
    ]
    failed = 0
    for raw, expected in cases:
        got = _norm_tx(raw)
        if got != expected:
            print(f"FAIL _norm_tx({raw!r}) -> {got}, expected {expected}")
            failed += 1
    assert failed == 0, f"{failed} cases failed"
    print(f"PASS all {len(cases)} transmission normalizations")


if __name__ == "__main__":
    test_norm_fuel()
    test_norm_tx()
    print("\nAll normalizer tests pass")
