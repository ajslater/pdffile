"""
Image-dominant page detection + extraction.

Synthetic fixtures cover the matrix of pages the detector needs to
classify correctly:

* full-bleed JPEG (IMAGE_DIRECT)
* full-bleed PNG (IMAGE_DIRECT)
* full-bleed CMYK JPEG (IMAGE_TRANSCODE)
* small inset image, mostly margin (PDF_FALLBACK — low coverage)
* image plus significant vector text (PDF_FALLBACK — text gate)
* two images on one page (PDF_FALLBACK — multi-image gate)
* image plus drawing (PDF_FALLBACK — drawings gate)
* rotated full-bleed JPEG (IMAGE_TRANSCODE — extraction must apply
  /Rotate, i.e. match the page's displayed orientation)
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pymupdf
import pytest
from PIL import Image

from pdffile import PageFormat, PageMode, PDFFile

if TYPE_CHECKING:
    from pathlib import Path

# ── Synthetic fixture builders ────────────────────────────────────


def _solid_jpeg(size: tuple[int, int] = (300, 400), color: str = "RGB") -> bytes:
    """Build a tiny solid-color JPEG."""
    img = Image.new(color, size, (200, 50, 50) if color == "RGB" else 100)
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _solid_png(size: tuple[int, int] = (300, 400), color: str = "RGB") -> bytes:
    """Build a tiny solid-color PNG."""
    img = Image.new(color, size, (50, 200, 50))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _solid_cmyk_jpeg(size: tuple[int, int] = (300, 400)) -> bytes:
    """Build a CMYK JPEG to exercise the transcode path."""
    img = Image.new("CMYK", size, (50, 50, 200, 0))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _two_tone_jpeg(size: tuple[int, int] = (300, 400)) -> bytes:
    """Red top half, blue bottom half — makes orientation detectable."""
    img = Image.new("RGB", size, (200, 50, 50))
    img.paste((50, 50, 200), (0, size[1] // 2, size[0], size[1]))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _top_bottom_colors(blob: bytes) -> tuple[tuple, tuple]:
    """Sample pixels near the top and bottom edges of a JPEG."""
    img = Image.open(io.BytesIO(blob)).convert("RGB")
    w, h = img.size
    top = img.getpixel((w // 2, h // 20))
    bottom = img.getpixel((w // 2, h - 1 - h // 20))
    # ``getpixel`` on an RGB image always yields a tuple; narrow the
    # stub's ``float | tuple | None`` union for the type checker.
    assert isinstance(top, tuple)
    assert isinstance(bottom, tuple)
    return top, bottom


#: Channel threshold separating the red half from the blue half after
#: JPEG compression (nominal values are 200 vs 50).
_CHANNEL_THRESHOLD = 120

#: /Rotate value used by the ``rotated`` fixture.
_ROTATED_FIXTURE_DEGREES = 90


def _is_reddish(px: tuple) -> bool:
    return px[0] > _CHANNEL_THRESHOLD and px[2] < _CHANNEL_THRESHOLD


def _is_bluish(px: tuple) -> bool:
    return px[2] > _CHANNEL_THRESHOLD and px[0] < _CHANNEL_THRESHOLD


def _new_pdf(tmp_path: Path, name: str) -> tuple[pymupdf.Document, Path]:
    """Open a fresh PDF document with a stable on-disk path."""
    path = tmp_path / name
    doc = pymupdf.open()  # type: ignore[attr-defined]
    return doc, path


def _save(doc: pymupdf.Document, path: Path) -> Path:
    doc.save(path)
    doc.close()
    return path


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def image_dominant_jpeg(tmp_path: Path) -> Path:
    """One page, a full-bleed JPEG, no text, no drawings."""
    doc, path = _new_pdf(tmp_path, "image_dominant_jpeg.pdf")
    page = doc.new_page(width=300, height=400)  # type: ignore[attr-defined]
    page.insert_image(page.rect, stream=_solid_jpeg())
    return _save(doc, path)


@pytest.fixture
def image_dominant_png(tmp_path: Path) -> Path:
    """One page, a full-bleed PNG."""
    doc, path = _new_pdf(tmp_path, "image_dominant_png.pdf")
    page = doc.new_page(width=300, height=400)  # type: ignore[attr-defined]
    page.insert_image(page.rect, stream=_solid_png())
    return _save(doc, path)


@pytest.fixture
def image_dominant_cmyk(tmp_path: Path) -> Path:
    """One page, a full-bleed CMYK JPEG — needs transcode."""
    doc, path = _new_pdf(tmp_path, "image_dominant_cmyk.pdf")
    page = doc.new_page(width=300, height=400)  # type: ignore[attr-defined]
    page.insert_image(page.rect, stream=_solid_cmyk_jpeg())
    return _save(doc, path)


@pytest.fixture
def small_inset(tmp_path: Path) -> Path:
    """One page, an image covering only ~10% of the page rect."""
    doc, path = _new_pdf(tmp_path, "small_inset.pdf")
    page = doc.new_page(width=600, height=800)  # type: ignore[attr-defined]
    inset = pymupdf.Rect(50, 50, 200, 250)  # type: ignore[attr-defined]
    page.insert_image(inset, stream=_solid_jpeg())
    return _save(doc, path)


@pytest.fixture
def image_plus_text(tmp_path: Path) -> Path:
    """Full-bleed image with a large block of vector text drawn over it."""
    doc, path = _new_pdf(tmp_path, "image_plus_text.pdf")
    page = doc.new_page(width=300, height=400)  # type: ignore[attr-defined]
    page.insert_image(page.rect, stream=_solid_jpeg())
    page.insert_text(
        (20, 60),
        (
            "lorem ipsum dolor sit amet consectetur adipiscing elit"
            " sed do eiusmod tempor incididunt ut labore et dolore magna"
        ),
        fontsize=8,
    )
    return _save(doc, path)


@pytest.fixture
def two_images(tmp_path: Path) -> Path:
    """Page split into two side-by-side images."""
    doc, path = _new_pdf(tmp_path, "two_images.pdf")
    page = doc.new_page(width=600, height=400)  # type: ignore[attr-defined]
    left = pymupdf.Rect(0, 0, 300, 400)  # type: ignore[attr-defined]
    right = pymupdf.Rect(300, 0, 600, 400)  # type: ignore[attr-defined]
    page.insert_image(left, stream=_solid_jpeg())
    page.insert_image(right, stream=_solid_jpeg())
    return _save(doc, path)


@pytest.fixture
def image_plus_drawing(tmp_path: Path) -> Path:
    """Image with a vector line drawn over it."""
    doc, path = _new_pdf(tmp_path, "image_plus_drawing.pdf")
    page = doc.new_page(width=300, height=400)  # type: ignore[attr-defined]
    page.insert_image(page.rect, stream=_solid_jpeg())
    page.draw_line((10, 10), (290, 390), color=(0, 0, 0), width=2)
    return _save(doc, path)


@pytest.fixture
def vector_only(tmp_path: Path) -> Path:
    """Pure vector text page — no embedded images."""
    doc, path = _new_pdf(tmp_path, "vector_only.pdf")
    page = doc.new_page(width=300, height=400)  # type: ignore[attr-defined]
    page.insert_text((20, 60), "Hello, world.", fontsize=12)
    return _save(doc, path)


@pytest.fixture
def rotated(tmp_path: Path) -> Path:
    """Image-dominant page with /Rotate 90."""
    doc, path = _new_pdf(tmp_path, "rotated.pdf")
    page = doc.new_page(width=300, height=400)  # type: ignore[attr-defined]
    page.insert_image(page.rect, stream=_solid_jpeg())
    page.set_rotation(90)
    return _save(doc, path)


@pytest.fixture
def rotated_180(tmp_path: Path) -> Path:
    """
    Image-dominant page stored upside down, righted by /Rotate 180.

    Mirrors scanner output that stores each scan inverted and relies
    on the page rotation attribute for display. The stored image has
    a red top; the *displayed* page has a blue top.
    """
    doc, path = _new_pdf(tmp_path, "rotated_180.pdf")
    page = doc.new_page(width=300, height=400)  # type: ignore[attr-defined]
    page.insert_image(page.rect, stream=_two_tone_jpeg())
    page.set_rotation(180)
    return _save(doc, path)


# ── classify_page ─────────────────────────────────────────────────


def test_classify_image_dominant_jpeg(image_dominant_jpeg: Path) -> None:
    """Plain JPEG full-bleed → IMAGE_DIRECT, ext=jpeg."""
    pdf = PDFFile(image_dominant_jpeg)
    try:
        v = pdf.classify_page(0)
    finally:
        pdf.close()
    assert v.mode is PageMode.IMAGE_DIRECT
    assert v.ext == "jpeg"
    assert v.image_xref is not None


def test_classify_image_dominant_png(image_dominant_png: Path) -> None:
    """PNG full-bleed → IMAGE_DIRECT, ext=png."""
    pdf = PDFFile(image_dominant_png)
    try:
        v = pdf.classify_page(0)
    finally:
        pdf.close()
    assert v.mode is PageMode.IMAGE_DIRECT
    assert v.ext == "png"


def test_classify_cmyk_image_needs_transcode(image_dominant_cmyk: Path) -> None:
    """CMYK colorspace → IMAGE_TRANSCODE (browser unsafe as-stored)."""
    pdf = PDFFile(image_dominant_cmyk)
    try:
        v = pdf.classify_page(0)
    finally:
        pdf.close()
    assert v.mode is PageMode.IMAGE_TRANSCODE


def test_classify_small_inset_falls_through(small_inset: Path) -> None:
    """Image covering <85% → PDF_FALLBACK (coverage gate)."""
    pdf = PDFFile(small_inset)
    try:
        v = pdf.classify_page(0)
    finally:
        pdf.close()
    assert v.mode is PageMode.PDF_FALLBACK


def test_classify_image_plus_text_falls_through(image_plus_text: Path) -> None:
    """Visible vector text → PDF_FALLBACK (text gate)."""
    pdf = PDFFile(image_plus_text)
    try:
        v = pdf.classify_page(0)
    finally:
        pdf.close()
    assert v.mode is PageMode.PDF_FALLBACK


def test_classify_two_images_falls_through(two_images: Path) -> None:
    """Multi-image page → PDF_FALLBACK (image-count gate)."""
    pdf = PDFFile(two_images)
    try:
        v = pdf.classify_page(0)
    finally:
        pdf.close()
    assert v.mode is PageMode.PDF_FALLBACK


def test_classify_image_plus_drawing_falls_through(image_plus_drawing: Path) -> None:
    """Vector ink on the page → PDF_FALLBACK (drawings gate)."""
    pdf = PDFFile(image_plus_drawing)
    try:
        v = pdf.classify_page(0)
    finally:
        pdf.close()
    assert v.mode is PageMode.PDF_FALLBACK


def test_classify_vector_only_falls_through(vector_only: Path) -> None:
    """No images → PDF_FALLBACK."""
    pdf = PDFFile(vector_only)
    try:
        v = pdf.classify_page(0)
    finally:
        pdf.close()
    assert v.mode is PageMode.PDF_FALLBACK


def test_classify_rotated_needs_transcode(rotated: Path) -> None:
    """Rotated page → IMAGE_TRANSCODE (extracted bytes lack rotation)."""
    pdf = PDFFile(rotated)
    try:
        v = pdf.classify_page(0)
    finally:
        pdf.close()
    assert v.mode is PageMode.IMAGE_TRANSCODE
    assert v.rotation == _ROTATED_FIXTURE_DEGREES
    assert v.page_index == 0


# ── read_image_if_dominant ────────────────────────────────────────


def test_read_image_if_dominant_returns_jpeg(image_dominant_jpeg: Path) -> None:
    """JPEG full-bleed → returns embedded JPEG bytes."""
    pdf = PDFFile(image_dominant_jpeg)
    try:
        result = pdf.read_image_if_dominant(0)
    finally:
        pdf.close()
    assert result is not None
    blob, ext = result
    assert ext == "jpeg"
    assert blob[:3] == b"\xff\xd8\xff", "JPEG SOI marker missing"
    # Bytes decode as a real JPEG.
    img = Image.open(io.BytesIO(blob))
    assert img.format == "JPEG"
    assert img.mode in {"RGB", "L"}


def test_read_image_if_dominant_returns_png(image_dominant_png: Path) -> None:
    """PNG full-bleed → returns embedded PNG bytes."""
    pdf = PDFFile(image_dominant_png)
    try:
        result = pdf.read_image_if_dominant(0)
    finally:
        pdf.close()
    assert result is not None
    blob, ext = result
    assert ext == "png"
    assert blob[:8] == b"\x89PNG\r\n\x1a\n", "PNG signature missing"


def test_read_image_if_dominant_transcodes_cmyk(image_dominant_cmyk: Path) -> None:
    """CMYK input → transcoded RGB JPEG (browser-safe)."""
    pdf = PDFFile(image_dominant_cmyk)
    try:
        result = pdf.read_image_if_dominant(0)
    finally:
        pdf.close()
    assert result is not None
    blob, ext = result
    assert ext == "jpeg"
    img = Image.open(io.BytesIO(blob))
    assert img.format == "JPEG"
    assert img.mode == "RGB", f"expected RGB after transcode, got {img.mode}"


def test_read_image_if_dominant_returns_none_on_fallback(vector_only: Path) -> None:
    """Vector page → None (caller falls through to PDF path)."""
    pdf = PDFFile(vector_only)
    try:
        result = pdf.read_image_if_dominant(0)
    finally:
        pdf.close()
    assert result is None


def test_read_image_if_dominant_applies_180_rotation(rotated_180: Path) -> None:
    """/Rotate 180 page → extraction matches the displayed orientation."""
    pdf = PDFFile(rotated_180)
    try:
        result = pdf.read_image_if_dominant(0)
    finally:
        pdf.close()
    assert result is not None
    blob, ext = result
    assert ext == "jpeg"
    top, bottom = _top_bottom_colors(blob)
    assert _is_bluish(top), f"top should be blue after /Rotate 180, got {top}"
    assert _is_reddish(bottom), f"bottom should be red after /Rotate 180, got {bottom}"


def test_read_image_if_dominant_applies_90_rotation(rotated: Path) -> None:
    """/Rotate 90 page → extraction is landscape like the displayed page."""
    pdf = PDFFile(rotated)
    try:
        result = pdf.read_image_if_dominant(0)
    finally:
        pdf.close()
    assert result is not None
    blob, ext = result
    assert ext == "jpeg"
    img = Image.open(io.BytesIO(blob))
    assert img.width > img.height, (
        f"expected landscape after /Rotate 90, got {img.size}"
    )


# ── read_full_pixmap_jpeg ─────────────────────────────────────────


def test_read_full_pixmap_jpeg_on_vector_page(vector_only: Path) -> None:
    """Force-image rasterizes vector pages to JPEG."""
    pdf = PDFFile(vector_only)
    try:
        blob, ext = pdf.read_full_pixmap_jpeg(0)
    finally:
        pdf.close()
    assert ext == "jpeg"
    assert blob[:3] == b"\xff\xd8\xff"
    img = Image.open(io.BytesIO(blob))
    assert img.mode == "RGB"


def test_read_full_pixmap_jpeg_short_circuits_for_image_dominant(
    image_dominant_jpeg: Path,
) -> None:
    """When the page is image-dominant, returns the embedded JPEG cheaply."""
    pdf = PDFFile(image_dominant_jpeg)
    try:
        blob, ext = pdf.read_full_pixmap_jpeg(0)
    finally:
        pdf.close()
    # Should be the embedded JPEG (same first bytes), not a re-render.
    assert ext == "jpeg"
    assert blob[:3] == b"\xff\xd8\xff"


def test_read_full_pixmap_jpeg_applies_180_rotation(rotated_180: Path) -> None:
    """Forced-image serve of a /Rotate 180 page matches the display."""
    pdf = PDFFile(rotated_180)
    try:
        blob, ext = pdf.read_full_pixmap_jpeg(0)
    finally:
        pdf.close()
    assert ext == "jpeg"
    top, bottom = _top_bottom_colors(blob)
    assert _is_bluish(top), f"top should be blue after /Rotate 180, got {top}"
    assert _is_reddish(bottom), f"bottom should be red after /Rotate 180, got {bottom}"


# ── read() integration via PageFormat.IMAGE_IF_DOMINANT ──────────


def test_read_image_if_dominant_format_returns_image(
    image_dominant_jpeg: Path,
) -> None:
    """``fmt=image_if_dominant`` writes ``ext=jpeg`` to props for matched page."""
    pdf = PDFFile(image_dominant_jpeg)
    props: dict = {}
    try:
        blob = pdf.read("0", fmt=PageFormat.IMAGE_IF_DOMINANT.value, props=props)
    finally:
        pdf.close()
    assert props["ext"] == "jpeg"
    assert blob[:3] == b"\xff\xd8\xff"


def test_read_image_if_dominant_format_falls_through(vector_only: Path) -> None:
    """``fmt=image_if_dominant`` writes ``ext=pdf`` when detector declines."""
    pdf = PDFFile(vector_only)
    props: dict = {}
    try:
        blob = pdf.read("0", fmt=PageFormat.IMAGE_IF_DOMINANT.value, props=props)
    finally:
        pdf.close()
    assert props["ext"] == "pdf"
    assert blob[:5] == b"%PDF-", "expected PDF magic on fall-through"


def test_read_pixmap_jpeg_format_always_returns_jpeg(vector_only: Path) -> None:
    """``fmt=pixmap_jpeg`` always returns JPEG, even on vector pages."""
    pdf = PDFFile(vector_only)
    props: dict = {}
    try:
        blob = pdf.read("0", fmt=PageFormat.PIXMAP_JPEG.value, props=props)
    finally:
        pdf.close()
    assert props["ext"] == "jpeg"
    assert blob[:3] == b"\xff\xd8\xff"
