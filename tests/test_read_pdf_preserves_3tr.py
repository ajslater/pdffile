"""
``read_pdf`` must preserve the ``3 Tr`` invisible-text operator.

Acrobat-OCR'd PDFs put the OCR overlay in text rendering mode 3
(invisible) so it's selectable but not drawn. ``Document.convert_to_pdf``
rebuilds the page and drops those operators — the OCR text becomes
visible against the page raster, "doubling up." ``insert_pdf`` copies
the page faithfully and keeps the operator. This test guards against a
regression to the ``convert_to_pdf`` path.

The fixture is a 627-byte hand-coded PDF with ``3 Tr`` followed by a
text-show operator on a 200x200 page; that's the smallest possible
shape that makes the bug visible.
"""

from pathlib import Path

import pymupdf

from pdffile import PDFFile

_FIXTURE = Path(__file__).parent / "test_invisible_text.pdf"


def _tr_modes(content: bytes) -> list[bytes]:
    """Return text rendering mode operands found in a content stream."""
    import re

    return re.findall(rb"(\d+)\s+Tr\b", content)


def test_fixture_has_invisible_text():
    """Sanity check on the fixture itself."""
    doc = pymupdf.open(_FIXTURE)
    try:
        assert doc.page_count == 1
        modes = _tr_modes(doc[0].read_contents())
        assert modes == [b"3"], f"expected [b'3'], got {modes}"
    finally:
        doc.close()


def test_read_pdf_preserves_invisible_text_mode():
    """``read_pdf`` output keeps the ``3 Tr`` operator."""
    pdf = PDFFile(_FIXTURE)
    try:
        out_bytes, ext = pdf.read_pdf(0)
    finally:
        pdf.close()
    assert ext == "pdf"
    out = pymupdf.open(stream=out_bytes, filetype="pdf")
    try:
        modes = _tr_modes(out[0].read_contents())
        assert modes == [b"3"], (
            f"read_pdf stripped the invisible-text mode (got {modes}); "
            "this regresses to the convert_to_pdf path that corrupts "
            "Acrobat-OCR'd PDFs"
        )
    finally:
        out.close()


def test_read_pdf_renders_identically_to_source():
    """Single-page extract via read_pdf must render pixel-identically."""
    src = pymupdf.open(_FIXTURE)
    try:
        src_pix = src[0].get_pixmap().tobytes("ppm")
    finally:
        src.close()

    pdf = PDFFile(_FIXTURE)
    try:
        out_bytes, _ = pdf.read_pdf(0)
    finally:
        pdf.close()

    out = pymupdf.open(stream=out_bytes, filetype="pdf")
    try:
        out_pix = out[0].get_pixmap().tobytes("ppm")
    finally:
        out.close()

    assert out_pix == src_pix
