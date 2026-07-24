"""
``read_pdf`` reads an inclusive page range as one multi-page pdf.

Callers extracting a range of pages want a single document, not one
file per page. ``insert_pdf`` already takes ``from_page``/``to_page``,
so the range is a copy of the same faithful-page path the single page
read uses.

The fixture is the 4 page ``test_pdf.pdf``, pages ``0``-``3``.
"""

from pathlib import Path

import pymupdf
import pytest

from pdffile import PDFFile

_FIXTURE = Path(__file__).parent / "test_pdf.pdf"
_FIXTURE_PAGE_COUNT = 4
_RANGE_PAGE_COUNT = 3


def _page_pixmaps(doc: pymupdf.Document) -> list[bytes]:
    """Render every page for content comparison."""
    return [page.get_pixmap().tobytes("ppm") for page in doc]


def test_read_pdf_range_pages_match_source():
    """A range holds exactly the source pages, in order."""
    src = pymupdf.open(_FIXTURE)
    try:
        src_pixmaps = _page_pixmaps(src)[1:4]
    finally:
        src.close()

    pdf = PDFFile(_FIXTURE)
    try:
        out_bytes, ext = pdf.read_pdf(1, 3)
    finally:
        pdf.close()

    assert ext == "pdf"
    out = pymupdf.open(stream=out_bytes, filetype="pdf")
    try:
        assert out.page_count == _RANGE_PAGE_COUNT
        assert _page_pixmaps(out) == src_pixmaps
    finally:
        out.close()


def test_read_pdf_single_page_unchanged():
    """Omitting the end page reads one page, as it always has."""
    pdf = PDFFile(_FIXTURE)
    try:
        single_bytes, _ = pdf.read_pdf(2)
        same_page_range_bytes, _ = pdf.read_pdf(2, 2)
    finally:
        pdf.close()

    assert single_bytes == same_page_range_bytes
    out = pymupdf.open(stream=single_bytes, filetype="pdf")
    try:
        assert out.page_count == 1
    finally:
        out.close()


def test_read_pdf_full_range():
    """A range spanning the whole document copies every page."""
    pdf = PDFFile(_FIXTURE)
    try:
        out_bytes, _ = pdf.read_pdf(0, 3)
    finally:
        pdf.close()

    out = pymupdf.open(stream=out_bytes, filetype="pdf")
    try:
        assert out.page_count == _FIXTURE_PAGE_COUNT
    finally:
        out.close()


def test_read_pdf_range_is_deterministic():
    """Repeated reads are byte identical, per ``no_new_id=True``."""
    pdf = PDFFile(_FIXTURE)
    try:
        first, _ = pdf.read_pdf(0, 3)
        second, _ = pdf.read_pdf(0, 3)
    finally:
        pdf.close()

    assert first == second


def test_read_pdf_inverted_range():
    """An end page before the start page is an error, not a reversal."""
    pdf = PDFFile(_FIXTURE)
    try:
        with pytest.raises(ValueError, match="before start page"):
            pdf.read_pdf(2, 1)
    finally:
        pdf.close()
