"""
Close-time save semantics.

``PDFFile.close`` must save only when the caller wrote through the
public API (``writestr`` / ``remove`` / ``write_metadata``). MuPDF
marks a document dirty when it repairs malformed content streams in
memory during *read* operations (``get_text``, ``get_drawings`` —
both used by ``classify_page``), and saving on that signal rewrites
the user's file on disk from a read-only workflow.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pymupdf
from PIL import Image

from pdffile import PDFFile

if TYPE_CHECKING:
    from pathlib import Path


def _solid_jpeg(size: tuple[int, int] = (100, 150)) -> bytes:
    img = Image.new("RGB", size, (200, 50, 50))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _two_page_pdf(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    doc = pymupdf.open()  # type: ignore[attr-defined]
    for _ in range(2):
        page = doc.new_page(width=100, height=150)  # type: ignore[attr-defined]
        page.insert_image(page.rect, stream=_solid_jpeg())
    doc.save(path)
    doc.close()
    return path


def test_close_after_reads_does_not_rewrite_file(tmp_path: Path) -> None:
    """Read-only use never rewrites the file, even if MuPDF dirties the doc."""
    path = _two_page_pdf(tmp_path, "reads.pdf")
    before = path.read_bytes()
    pdf = PDFFile(path)
    pdf.classify_page(0)
    pdf.read_image_if_dominant(0)
    # Simulate MuPDF's in-memory stream repair: it flips
    # ``Document.is_dirty`` with no caller write, exactly as
    # ``get_text`` does on malformed scanner output.
    pdf._doc.load_page(0).clean_contents()
    assert pdf._doc.is_dirty
    pdf.close()
    assert path.read_bytes() == before, "read-only close must not rewrite the file"


def test_close_after_writestr_saves(tmp_path: Path) -> None:
    """An embedded-file write persists through close."""
    path = _two_page_pdf(tmp_path, "writestr.pdf")
    pdf = PDFFile(path)
    pdf.writestr("metadata.xml", b"<x/>")
    pdf.close()
    reopened = PDFFile(path)
    try:
        assert "metadata.xml" in reopened.namelist()
    finally:
        reopened.close()


def test_close_after_write_metadata_saves(tmp_path: Path) -> None:
    """A metadata write persists through close."""
    path = _two_page_pdf(tmp_path, "metadata.pdf")
    pdf = PDFFile(path)
    pdf.write_metadata({"title": "Boot Magazine"})
    pdf.close()
    reopened = PDFFile(path)
    try:
        assert reopened.get_metadata().get("title") == "Boot Magazine"
    finally:
        reopened.close()


def test_close_after_remove_saves(tmp_path: Path) -> None:
    """A page removal persists through close."""
    path = _two_page_pdf(tmp_path, "remove.pdf")
    pdf = PDFFile(path)
    pdf.remove("0")
    pdf.close()
    reopened = PDFFile(path)
    try:
        assert reopened.get_page_count() == 1
    finally:
        reopened.close()
