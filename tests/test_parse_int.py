"""Test _parse_int handles European decimal formats correctly."""
from scrapers.discovery.meili_enricher import _parse_int


def test_parse_int():
    cases = [
        ("23990", 23990),
        ("23 990", 23990),
        ("23.990", 23990),
        ("23,990", 23990),
        ("23.990,00", 23990),
        ("23,990.00", 23990),
        ("23 990,00", 23990),
        ("23\u00a0990", 23990),
        ("123.456", 123456),
        ("123,456", 123456),
        ("1.234.567,89", 1234567),
        ("invalid", None),
        ("", None),
    ]
    failed = 0
    for raw, expected in cases:
        got = _parse_int(raw)
        if got != expected:
            print(f"FAIL _parse_int({raw!r}) -> {got}, expected {expected}")
            failed += 1
        else:
            print(f"PASS _parse_int({raw!r}) -> {got}")
    assert failed == 0, f"{failed} cases failed"


if __name__ == "__main__":
    test_parse_int()
    print("\nAll _parse_int tests pass")
