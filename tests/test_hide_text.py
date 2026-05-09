"""Tests for the ``hide_text`` knob on read_pdf / read_pixmap / read."""

from pathlib import Path

import pymupdf

from pdffile import PageFormat, PDFFile

_FIXTURE = Path(__file__).parent / "test_pdf.pdf"


def test_pixmap_hide_text_changes_rendering():
    """``hide_text=True`` produces a different pixmap than the default."""
    pdf = PDFFile(_FIXTURE)
    try:
        baseline, _ = pdf.read_pixmap(0)
        hidden, _ = pdf.read_pixmap(0, hide_text=True)
        assert baseline != hidden
    finally:
        pdf.close()


def test_pixmap_hide_text_restores_source_doc():
    """A hide_text call must not leave the source document mutated."""
    pdf = PDFFile(_FIXTURE)
    try:
        baseline, _ = pdf.read_pixmap(0)
        pdf.read_pixmap(0, hide_text=True)
        restored, _ = pdf.read_pixmap(0)
        assert restored == baseline
    finally:
        pdf.close()


def test_pdf_hide_text_renders_differently():
    """The PDF returned with hide_text renders without visible text."""
    pdf = PDFFile(_FIXTURE)
    try:
        baseline, _ = pdf.read_pdf(0)
        hidden, _ = pdf.read_pdf(0, hide_text=True)
        # Bytes must differ — the prepended ``3 Tr`` op is in the hidden form.
        assert baseline != hidden
        with (
            pymupdf.open(stream=baseline, filetype="pdf") as base_doc,
            pymupdf.open(stream=hidden, filetype="pdf") as hidden_doc,
        ):
            # Text must remain extractable — we changed rendering mode,
            # not the text content itself.
            assert hidden_doc[0].get_text() == base_doc[0].get_text()
            base_pix = base_doc[0].get_pixmap().tobytes("ppm")
            hidden_pix = hidden_doc[0].get_pixmap().tobytes("ppm")
            assert base_pix != hidden_pix
    finally:
        pdf.close()


def test_read_dispatches_hide_text_to_pixmap_and_pdf():
    """``PDFFile.read`` forwards ``hide_text`` to the right backend."""
    pdf = PDFFile(_FIXTURE)
    try:
        # Pixmap path.
        baseline = pdf.read("0", fmt=PageFormat.PIXMAP.value)
        hidden = pdf.read("0", fmt=PageFormat.PIXMAP.value, hide_text=True)
        assert baseline != hidden
        # Default (PDF) path.
        baseline_pdf = pdf.read("0")
        hidden_pdf = pdf.read("0", hide_text=True)
        assert baseline_pdf != hidden_pdf
    finally:
        pdf.close()


def test_read_image_unaffected_by_hide_text():
    """The embedded-image path bypasses the content stream entirely."""
    pdf = PDFFile(_FIXTURE)
    try:
        # Use a fixture page that has no embedded image — the read()
        # fallback should land on read_pixmap, where hide_text *does*
        # change output. Sanity-check that the IMAGE path itself returns
        # identical bytes if it succeeds (i.e. for a page that has an
        # extractable embedded image). The test fixture has no images
        # so we only exercise the fallback path here.
        with_text = pdf.read("0", fmt=PageFormat.IMAGE.value)
        without_text = pdf.read("0", fmt=PageFormat.IMAGE.value, hide_text=True)
        # Fallback to pixmap means hide_text *does* take effect.
        assert with_text != without_text
    finally:
        pdf.close()
