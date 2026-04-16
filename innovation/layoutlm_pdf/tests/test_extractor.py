"""
test_extractor.py — Tests for LayoutLMv3 extractor (heuristic path + Go subprocess contract).

CI mode: runs without PDF system deps; fixture_pdf tests skip automatically.
"""

import json
import os
import subprocess
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from extractor import (
    _heuristic_entities,
    ExtractionResult,
    Entity,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")


class TestHeuristicEntities:
    def test_de_hrb(self):
        entities = _heuristic_entities("Handelsregister HRB 12345 München")
        assert "REGISTRATION_NUMBER" in {e.label for e in entities}
        assert any("HRB" in e.text for e in entities if e.label == "REGISTRATION_NUMBER")

    def test_fr_siren(self):
        entities = _heuristic_entities("SIREN: 123 456 789")
        assert "REGISTRATION_NUMBER" in {e.label for e in entities}

    def test_es_nif(self):
        entities = _heuristic_entities("NIF: A-12345678")
        assert "REGISTRATION_NUMBER" in {e.label for e in entities}

    def test_gmbh_name(self):
        entities = _heuristic_entities("Firma: Mustermann GmbH\nSitz: München")
        assert "COMPANY_NAME" in {e.label for e in entities}
        assert any("GmbH" in e.text for e in entities if e.label == "COMPANY_NAME")

    def test_sarl_name(self):
        entities = _heuristic_entities("Dénomination: Dupont SARL")
        assert "COMPANY_NAME" in {e.label for e in entities}

    def test_de_legal_rep(self):
        entities = _heuristic_entities("Geschäftsführer: Max Mustermann\nHRB 1")
        assert "LEGAL_REPRESENTATIVE" in {e.label for e in entities}

    def test_fr_legal_rep(self):
        entities = _heuristic_entities("gérant: Jean Dupont, SIREN 123 456 789")
        assert "LEGAL_REPRESENTATIVE" in {e.label for e in entities}

    def test_es_legal_rep(self):
        entities = _heuristic_entities("Administrador: Carlos García NIF A-1234567")
        assert "LEGAL_REPRESENTATIVE" in {e.label for e in entities}

    def test_confidence_range(self):
        entities = _heuristic_entities("HRB 99999 Mustermann GmbH Geschäftsführer: Hans Schmidt")
        for e in entities:
            assert 0.0 <= e.confidence <= 1.0


class TestExtractionResult:
    def test_json_schema(self):
        result = ExtractionResult(
            pdf_path="/tmp/test.pdf",
            method="heuristic",
            entities=[Entity(label="COMPANY_NAME", text="Test GmbH", confidence=0.80)],
        )
        data = json.loads(result.to_json())
        assert data["pdf_path"] == "/tmp/test.pdf"
        assert data["method"] == "heuristic"
        assert len(data["entities"]) == 1
        assert data["entities"][0]["label"] == "COMPANY_NAME"
        assert data["error"] is None

    def test_empty_entities(self):
        result = ExtractionResult(pdf_path="/tmp/x.pdf", method="error",
                                  error="not found")
        data = json.loads(result.to_json())
        assert data["entities"] == []
        assert data["error"] == "not found"


FIXTURE_CASES = [
    ("de_handelsregister.pdf", "REGISTRATION_NUMBER"),
    ("fr_extrait_kbis.pdf",    "REGISTRATION_NUMBER"),
    ("es_nota_simple.pdf",     "REGISTRATION_NUMBER"),
]


@pytest.mark.fixture_pdf
@pytest.mark.parametrize("filename,expected_label", FIXTURE_CASES)
def test_fixture_pdf_heuristic(filename, expected_label):
    pdf_path = os.path.join(FIXTURES_DIR, filename)
    if not os.path.exists(pdf_path):
        pytest.skip(f"fixture not generated: {filename}")

    from extractor import extract_entities
    result = extract_entities(pdf_path)
    labels = {e.label for e in result.entities}
    assert expected_label in labels, (
        f"{filename}: expected {expected_label} in {labels}; method={result.method}"
    )


def test_subprocess_stdout_is_json(tmp_path):
    fake_pdf = str(tmp_path / "nonexistent.pdf")
    extractor_path = os.path.join(os.path.dirname(__file__), "..", "extractor.py")
    result = subprocess.run(
        [sys.executable, extractor_path, "--pdf", fake_pdf],
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip(), "stdout must not be empty"
    data = json.loads(result.stdout)
    assert "pdf_path" in data
    assert "method" in data
    assert "entities" in data
    assert isinstance(data["entities"], list)
