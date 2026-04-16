"""
generate_fixtures.py — create minimal test PDFs for DE / FR / ES registry fixtures.

Run once:  python generate_fixtures.py
Produces:
  de_handelsregister.pdf   — synthetic DE HRB excerpt
  fr_kbis.pdf              — synthetic FR Kbis excerpt
  es_nota_simple.pdf       — synthetic ES Nota Simple excerpt

Each PDF is a single A4 page with plain text — no images needed.
Requires: reportlab (pip install reportlab)
If reportlab is not available, the fixtures are written as pre-encoded minimal PDFs.
"""

import os
from pathlib import Path

HERE = Path(__file__).parent

# Ground truth for tests
FIXTURES = {
    "de_handelsregister": {
        "company_name": "Autohaus München GmbH",
        "registration_number": "HRB 123456",
        "address": "Leopoldstraße 45, 80804 München",
        "legal_rep": "Hans Müller",
        "text": (
            "Amtsgericht München — Handelsregister B\n"
            "HRB 123456\n\n"
            "Autohaus München GmbH\n\n"
            "Sitz: Leopoldstraße 45, 80804 München\n\n"
            "Geschäftsführer: Hans Müller\n"
            "Stammkapital: 25.000,00 EUR\n"
            "Eingetragen am: 15.03.2012"
        ),
    },
    "fr_kbis": {
        "company_name": "Garage Renault Lyon Centre SARL",
        "registration_number": "542 107 651",
        "address": "12 Rue de la République, 69001 Lyon",
        "legal_rep": "Marie Dupont",
        "text": (
            "EXTRAIT Kbis\n"
            "Registre du Commerce et des Sociétés de Lyon\n\n"
            "SIREN: 542 107 651\n\n"
            "Garage Renault Lyon Centre SARL\n\n"
            "Siège social: 12 Rue de la République, 69001 Lyon\n\n"
            "Gérant: Marie Dupont\n"
            "Capital social: 15 000 EUR\n"
            "Date d'immatriculation: 22/06/2008"
        ),
    },
    "es_nota_simple": {
        "company_name": "Seat Concesionario Madrid Sur SL",
        "registration_number": "B-87654321",
        "address": "Calle Gran Vía 22, 28013 Madrid",
        "legal_rep": "Carlos García",
        "text": (
            "REGISTRO MERCANTIL DE MADRID\n"
            "NOTA SIMPLE INFORMATIVA\n\n"
            "NIF: B-87654321\n\n"
            "Seat Concesionario Madrid Sur SL\n\n"
            "Domicilio: Calle Gran Vía 22, 28013 Madrid\n\n"
            "Administrador: Carlos García\n"
            "Capital social: 18.000 EUR\n"
            "Fecha de constitución: 10/11/2015"
        ),
    },
}


def _write_pdf_reportlab(path: Path, text: str) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    c.setFont("Helvetica", 11)
    y = height - 60
    for line in text.splitlines():
        c.drawString(60, y, line)
        y -= 18
        if y < 60:
            break
    c.save()


def _write_minimal_pdf(path: Path, text: str) -> None:
    """Write a minimal valid PDF without reportlab."""
    # Embed text as PDF content stream (no fonts, plain text object)
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    lines = safe.splitlines()
    tf_lines = " ".join(f"({ln}) Tj T*" for ln in lines)

    stream_content = (
        "BT\n"
        "/F1 11 Tf\n"
        "60 770 Td\n"
        "14 TL\n"
        f"{tf_lines}\n"
        "ET"
    )
    stream_bytes = stream_content.encode("latin-1", errors="replace")

    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R "
        b"/MediaBox [0 0 595 842] /Contents 4 0 R /Resources "
        b"<< /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length "
        + str(len(stream_bytes)).encode()
        + b" >>\nstream\n"
        + stream_bytes
        + b"\nendstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n"
        b"0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000400 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
        b"startxref\n460\n%%EOF\n"
    )
    path.write_bytes(pdf)


def generate_all():
    for name, fixture in FIXTURES.items():
        out_path = HERE / f"{name}.pdf"
        if out_path.exists():
            print(f"  {out_path.name} already exists — skipping")
            continue
        try:
            _write_pdf_reportlab(out_path, fixture["text"])
            print(f"  {out_path.name} written (reportlab)")
        except ImportError:
            _write_minimal_pdf(out_path, fixture["text"])
            print(f"  {out_path.name} written (minimal PDF, reportlab not installed)")


if __name__ == "__main__":
    generate_all()
