"""
generate_fixtures.py — Create minimal DE/FR/ES registry PDF test fixtures.

Uses reportlab if available; falls back to raw PDF bytes.

Run: make layoutlm-fixtures
     OR python fixtures/generate_fixtures.py
"""

import os

FIXTURES_DIR = os.path.dirname(__file__)

FIXTURES = {
    "de_handelsregister.pdf": (
        "Handelsregister Auszug\n"
        "Firma: Mustermann GmbH\n"
        "HRB 12345\n"
        "Geschäftsführer: Max Mustermann\n"
        "Sitz: Musterstraße 1, 80333 München\n"
    ),
    "fr_extrait_kbis.pdf": (
        "Extrait Kbis\n"
        "Dénomination: Dupont SA\n"
        "SIREN: 123 456 789\n"
        "gérant: Jean Dupont\n"
        "Siège social: 1 rue de la Paix, 75001 Paris\n"
    ),
    "es_nota_simple.pdf": (
        "Nota Simple Informativa\n"
        "Denominación: García S.L.\n"
        "NIF: A-12345678\n"
        "Administrador: Carlos García\n"
        "Domicilio: Calle Mayor 10, 28013 Madrid\n"
    ),
}


def _write_raw_pdf(path: str, text: str) -> None:
    lines = text.strip().split("\n")
    stream_lines = []
    y = 750
    for line in lines:
        safe = line.replace("(", r"\(").replace(")", r"\)").replace("\\", "\\\\")
        stream_lines.append(f"BT /F1 12 Tf 50 {y} Td ({safe}) Tj ET")
        y -= 20
    stream = "\n".join(stream_lines)
    stream_bytes = stream.encode("latin-1", errors="replace")
    stream_len = len(stream_bytes)

    objects = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(
        f"3 0 obj\n<< /Type /Page /Parent 2 0 R "
        f"/MediaBox [0 0 595 842] /Contents 4 0 R "
        f"/Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n".encode()
    )
    objects.append(
        f"4 0 obj\n<< /Length {stream_len} >>\nstream\n".encode()
        + stream_bytes
        + b"\nendstream\nendobj\n"
    )
    objects.append(
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    )

    header = b"%PDF-1.4\n"
    body = b""
    offsets = []
    pos = len(header)
    for obj in objects:
        offsets.append(pos)
        body += obj
        pos += len(obj)

    xref_offset = len(header) + len(body)
    xref = f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        xref += f"{off:010d} 00000 n \n".encode()

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()

    with open(path, "wb") as f:
        f.write(header + body + xref + trailer)


def _write_reportlab_pdf(path: str, text: str) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(path, pagesize=A4)
    _, height = A4
    y = height - 60
    for line in text.strip().split("\n"):
        c.drawString(50, y, line)
        y -= 20
    c.save()


def generate_all() -> None:
    for filename, text in FIXTURES.items():
        path = os.path.join(FIXTURES_DIR, filename)
        try:
            _write_reportlab_pdf(path, text)
            print(f"  reportlab → {filename}")
        except ImportError:
            _write_raw_pdf(path, text)
            print(f"  raw PDF   → {filename}")


if __name__ == "__main__":
    generate_all()
