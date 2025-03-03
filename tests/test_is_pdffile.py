"""Simple test."""

from pdffile import PDFFile


def test_is_pdffile():
    """Simple test."""
    assert PDFFile.is_pdffile("./test_pdf.pdf")
