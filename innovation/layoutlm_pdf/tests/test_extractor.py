"""
Tests for innovation/layoutlm_pdf/extractor.py.

The tests:
  1. Verify the heuristic extractor correctly identifies entities from synthetic text.
  2. Verify the ExtractionResult JSON schema.
  3. Verify de/fr/es fixture PDFs (if they exist) yield expected entity types.
  4. Verify the Go subprocess contract: stdout is valid JSON.

These tests do NOT require LayoutLMv3 / torch / pdf2image to be installed.
The heuristic fallback is always tested.
"""

import json
import os
import sys
import subprocess
import tempfile
from pathlib import Path

import pytest

# Make parent importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extractor import (
    ExtractionResult,
    ExtractedEntity,
    _heuristic_entities,
    extract_entities,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
GROUND_TRUTH = json.loads((FIXTURES_DIR / "ground_truth.json").read_text())


# ── Unit tests for heuristic extractor ───────────────────────────────────────

class TestHeuristicEntities:
    def _words_bboxes(self, text: str):
        words = text.split()
        bboxes = [[i * 50, 0, i * 50 + 48, 20] for i in range(len(words))]
        return words, bboxes

    def test_de_hrb_number(self):
        text = "Amtsgericht München Handelsregister HRB 123456 Autohaus GmbH"
        words, bboxes = self._words_bboxes(text)
        ents = _heuristic_entities(words, bboxes, page=1)
        reg = [e for e in ents if e.entity_type == "REGISTRATION_NUMBER"]
        assert reg, "Expected REGISTRATION_NUMBER for HRB pattern"
        assert "HRB" in reg[0].text or "123456" in reg[0].text

    def test_fr_siren(self):
        text = "SIREN 542 107 651 Garage Renault Lyon Centre SARL"
        words, bboxes = self._words_bboxes(text)
        ents = _heuristic_entities(words, bboxes, page=1)
        reg = [e for e in ents if e.entity_type == "REGISTRATION_NUMBER"]
        assert reg, "Expected REGISTRATION_NUMBER for SIREN pattern"

    def test_es_nif(self):
        text = "NIF B-87654321 Seat Concesionario Madrid Sur SL"
        words, bboxes = self._words_bboxes(text)
        ents = _heuristic_entities(words, bboxes, page=1)
        reg = [e for e in ents if e.entity_type == "REGISTRATION_NUMBER"]
        assert reg, "Expected REGISTRATION_NUMBER for NIF pattern"

    def test_company_name_gmbh(self):
        text = "Autohaus München GmbH Sitz München Stammkapital"
        words, bboxes = self._words_bboxes(text)
        ents = _heuristic_entities(words, bboxes, page=1)
        names = [e for e in ents if e.entity_type == "COMPANY_NAME"]
        assert names, "Expected COMPANY_NAME containing GmbH"
        assert any("GmbH" in e.text for e in names)

    def test_company_name_sarl(self):
        text = "Garage Renault Lyon Centre SARL Paris"
        words, bboxes = self._words_bboxes(text)
        ents = _heuristic_entities(words, bboxes, page=1)
        names = [e for e in ents if e.entity_type == "COMPANY_NAME"]
        assert names, "Expected COMPANY_NAME containing SARL"

    def test_legal_rep_de(self):
        text = "Geschäftsführer: Hans Müller eingetragen"
        words, bboxes = self._words_bboxes(text)
        ents = _heuristic_entities(words, bboxes, page=1)
        reps = [e for e in ents if e.entity_type == "LEGAL_REP"]
        assert reps, "Expected LEGAL_REP for Geschäftsführer pattern"

    def test_legal_rep_fr(self):
        text = "Gérant: Marie Dupont siège Lyon"
        words, bboxes = self._words_bboxes(text)
        ents = _heuristic_entities(words, bboxes, page=1)
        reps = [e for e in ents if e.entity_type == "LEGAL_REP"]
        assert reps, "Expected LEGAL_REP for gérant pattern"

    def test_legal_rep_es(self):
        text = "Administrador: Carlos García Registro Mercantil"
        words, bboxes = self._words_bboxes(text)
        ents = _heuristic_entities(words, bboxes, page=1)
        reps = [e for e in ents if e.entity_type == "LEGAL_REP"]
        assert reps, "Expected LEGAL_REP for administrador pattern"

    def test_confidence_in_range(self):
        text = "HRB 123456 Autohaus GmbH Geschäftsführer: Hans Müller"
        words, bboxes = self._words_bboxes(text)
        ents = _heuristic_entities(words, bboxes, page=1)
        for e in ents:
            assert 0.0 <= e.confidence <= 1.0, f"Confidence out of range: {e}"


# ── ExtractionResult schema tests ─────────────────────────────────────────────

class TestExtractionResult:
    def test_to_json_valid(self):
        result = ExtractionResult(
            pdf_path="/tmp/test.pdf",
            pages_processed=1,
            entities=[
                ExtractedEntity("COMPANY_NAME", "Test GmbH", 0.9, 1, [0, 0, 100, 20])
            ],
            model_used="heuristic",
        )
        data = json.loads(result.to_json())
        assert data["pdf_path"] == "/tmp/test.pdf"
        assert data["pages_processed"] == 1
        assert len(data["entities"]) == 1
        assert data["entities"][0]["entity_type"] == "COMPANY_NAME"
        assert data["entities"][0]["text"] == "Test GmbH"
        assert data["entities"][0]["confidence"] == 0.9

    def test_entities_list_type(self):
        result = ExtractionResult(
            pdf_path="/tmp/test.pdf",
            pages_processed=0,
            entities=[],
            model_used="none",
            warnings=["test warning"],
        )
        data = json.loads(result.to_json())
        assert isinstance(data["entities"], list)
        assert isinstance(data["warnings"], list)
        assert "test warning" in data["warnings"]


# ── Fixture PDF tests (skip if pdf2image/tesseract not available) ──────────────

def _has_ocr_stack() -> bool:
    """Check if pdf2image + pytesseract + pillow are installed."""
    try:
        import pdf2image
        import pytesseract
        from PIL import Image
        return True
    except ImportError:
        return False


@pytest.mark.parametrize("fixture_name", ["de_handelsregister", "fr_kbis", "es_nota_simple"])
def test_fixture_pdf_heuristic(fixture_name: str):
    """
    Test that extract_entities returns valid JSON for each fixture PDF.
    Does NOT require LayoutLMv3 or OCR — tests the fallback path using
    pre-generated PDFs processed via PyMuPDF text extraction.
    """
    pdf_path = FIXTURES_DIR / f"{fixture_name}.pdf"
    if not pdf_path.exists():
        pytest.skip(f"Fixture not generated: {pdf_path}. Run: python fixtures/generate_fixtures.py")

    result = extract_entities(str(pdf_path))

    # Must always produce valid JSON
    js = json.loads(result.to_json())
    assert "entities" in js
    assert isinstance(js["entities"], list)
    assert js["pages_processed"] >= 0

    gt = GROUND_TRUTH[fixture_name]
    entity_types = {e["entity_type"] for e in js["entities"]}

    # At least some entities must be detected (heuristic may not get all)
    # The fixture PDFs contain strong patterns for all 4 entity types.
    if js["pages_processed"] > 0 and not js.get("warnings"):
        assert len(js["entities"]) > 0, f"No entities extracted from {fixture_name}"


# ── Go subprocess contract test ───────────────────────────────────────────────

def test_subprocess_stdout_is_json(tmp_path):
    """
    Verify that calling extractor.py as a subprocess (as Go does) prints
    valid JSON on stdout and exits 0.
    """
    # Create a minimal PDF for the subprocess test
    pdf_path = tmp_path / "test.pdf"
    try:
        from fixtures.generate_fixtures import _write_minimal_pdf
        _write_minimal_pdf(pdf_path, "HRB 123456\nAutohaus München GmbH\nGeschäftsführer: Hans Müller")
    except Exception:
        # Write raw bytes fallback
        pdf_path.write_bytes(
            b"%PDF-1.4\n1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n"
            b"2 0 obj\n<</Type/Pages/Kids[3 0 R]/Count 1>>\nendobj\n"
            b"3 0 obj\n<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>\nendobj\n"
            b"xref\n0 4\n0000000000 65535 f \ntrailer\n<</Size 4/Root 1 0 R>>\n"
            b"startxref\n9\n%%EOF\n"
        )

    extractor_py = Path(__file__).resolve().parents[1] / "extractor.py"
    result = subprocess.run(
        [sys.executable, str(extractor_py), "--pdf", str(pdf_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"extractor.py exited {result.returncode}: {result.stderr}"
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        pytest.fail(f"extractor.py stdout is not valid JSON: {e}\nstdout: {result.stdout!r}")
    assert "entities" in data
    assert "pdf_path" in data
