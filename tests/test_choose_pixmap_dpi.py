"""
Tests for auto-DPI page rasterization.

Covers ``choose_pixmap_dpi`` and the ``dpi`` parameter on
``PDFFile.read_full_pixmap_jpeg``. The detector picks a render DPI
matching the page's embedded-image resolution. Pages with no images
return the default; pages with hi-res scans return the scan's native
DPI; outliers (1-px tracking pixels, absurdly hi-DPI logos) are
filtered or capped.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pymupdf
import pytest
from PIL import Image

from pdffile import (
    DEFAULT_PIXMAP_DPI,
    MAX_PIXMAP_DPI,
    PDFFile,
    choose_pixmap_dpi,
)

if TYPE_CHECKING:
    from pathlib import Path

# Allow ±2 DPI tolerance for rounding inside the bbox math.
_DPI_200_LO = 198
_DPI_200_HI = 202

# Custom default/cap overrides used in parameter tests.
_OVERRIDE_DEFAULT_LOW = 72
_OVERRIDE_CAP_LOW = 200


# ── Helpers ───────────────────────────────────────────────────────


def _solid_jpeg(size: tuple[int, int]) -> bytes:
    """Return a tiny solid-color JPEG of the requested dimensions."""
    img = Image.new("RGB", size, (200, 50, 50))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _new_pdf(tmp_path: Path, name: str) -> tuple[pymupdf.Document, Path]:
    path = tmp_path / name
    doc = pymupdf.open()  # type: ignore[attr-defined]
    return doc, path


def _save(doc: pymupdf.Document, path: Path) -> Path:
    doc.save(path)
    doc.close()
    return path


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def blank_page(tmp_path: Path) -> Path:
    """One page, no images, no text — the empty case."""
    doc, path = _new_pdf(tmp_path, "blank.pdf")
    doc.new_page(width=300, height=400)  # type: ignore[attr-defined]
    return _save(doc, path)


@pytest.fixture
def vector_text_page(tmp_path: Path) -> Path:
    """Pure vector text — no images for the detector to measure."""
    doc, path = _new_pdf(tmp_path, "vector.pdf")
    page = doc.new_page(width=300, height=400)  # type: ignore[attr-defined]
    page.insert_text((20, 60), "Hello", fontsize=12)
    return _save(doc, path)


@pytest.fixture
def image_at_native_72_dpi(tmp_path: Path) -> Path:
    """
    Image whose pixel dims equal its bbox in points — 72 DPI native.

    Falls below the default; ``choose_pixmap_dpi`` should still
    return ``DEFAULT_PIXMAP_DPI`` (the floor).
    """
    doc, path = _new_pdf(tmp_path, "low_dpi.pdf")
    page = doc.new_page(width=600, height=800)  # type: ignore[attr-defined]
    # 600x800 px image placed at 600x800 points → 72 DPI native
    page.insert_image(page.rect, stream=_solid_jpeg((600, 800)))
    return _save(doc, path)


@pytest.fixture
def image_at_native_200_dpi(tmp_path: Path) -> Path:
    """200 DPI native — auto-DPI should pick 200."""
    doc, path = _new_pdf(tmp_path, "mid_dpi.pdf")
    page = doc.new_page(width=300, height=400)  # type: ignore[attr-defined]
    # 300pt = 4.166in. 4.166in * 200 DPI = 833 px.
    page.insert_image(page.rect, stream=_solid_jpeg((833, 1111)))
    return _save(doc, path)


@pytest.fixture
def image_above_cap(tmp_path: Path) -> Path:
    """
    Image that would compute >300 DPI — should clamp to MAX_PIXMAP_DPI.

    100x100 pt bbox with a 1500x1500 image → 1080 DPI.
    """
    doc, path = _new_pdf(tmp_path, "high_dpi.pdf")
    page = doc.new_page(width=400, height=400)  # type: ignore[attr-defined]
    inset = pymupdf.Rect(0, 0, 100, 100)  # type: ignore[attr-defined]
    page.insert_image(inset, stream=_solid_jpeg((1500, 1500)))
    return _save(doc, path)


@pytest.fixture
def negligible_image_only(tmp_path: Path) -> Path:
    """
    Build a page whose only image is too small to count.

    The image is well below ``min_bbox_fraction``, so the filter
    should ignore it; default DPI should win.
    """
    doc, path = _new_pdf(tmp_path, "negligible.pdf")
    page = doc.new_page(width=600, height=800)  # type: ignore[attr-defined]
    # 5x5 pt image on a 600x800 page = 0.005% of page area
    tiny = pymupdf.Rect(10, 10, 15, 15)  # type: ignore[attr-defined]
    page.insert_image(tiny, stream=_solid_jpeg((300, 300)))  # huge native DPI
    return _save(doc, path)


@pytest.fixture
def two_different_dpi_images(tmp_path: Path) -> Path:
    """
    Two images on one page — one ~100 DPI, one ~200 DPI.

    The max wins (200), since callers want the highest-fidelity
    render.
    """
    doc, path = _new_pdf(tmp_path, "mixed_dpi.pdf")
    page = doc.new_page(width=600, height=400)  # type: ignore[attr-defined]
    # Left half: 300pt wide, 400pt tall → 4.16x5.55in.
    # 100 DPI native → 416x555 px image.
    left = pymupdf.Rect(0, 0, 300, 400)  # type: ignore[attr-defined]
    page.insert_image(left, stream=_solid_jpeg((416, 555)))
    # Right half: same bbox size, 200 DPI native.
    right = pymupdf.Rect(300, 0, 600, 400)  # type: ignore[attr-defined]
    page.insert_image(right, stream=_solid_jpeg((833, 1111)))
    return _save(doc, path)


# ── choose_pixmap_dpi ─────────────────────────────────────────────


def test_blank_page_returns_default(blank_page: Path) -> None:
    """No images → default DPI."""
    pdf = PDFFile(blank_page)
    try:
        page = pdf._doc.load_page(0)
        dpi = choose_pixmap_dpi(page)
    finally:
        pdf.close()
    assert dpi == DEFAULT_PIXMAP_DPI


def test_vector_text_returns_default(vector_text_page: Path) -> None:
    """Vector text with no images → default DPI."""
    pdf = PDFFile(vector_text_page)
    try:
        page = pdf._doc.load_page(0)
        dpi = choose_pixmap_dpi(page)
    finally:
        pdf.close()
    assert dpi == DEFAULT_PIXMAP_DPI


def test_low_dpi_image_floors_at_default(image_at_native_72_dpi: Path) -> None:
    """Image native DPI below default → floor at default."""
    pdf = PDFFile(image_at_native_72_dpi)
    try:
        page = pdf._doc.load_page(0)
        dpi = choose_pixmap_dpi(page)
    finally:
        pdf.close()
    assert dpi == DEFAULT_PIXMAP_DPI


def test_mid_dpi_image_returns_native(image_at_native_200_dpi: Path) -> None:
    """200 DPI native image → ~200 DPI returned."""
    pdf = PDFFile(image_at_native_200_dpi)
    try:
        page = pdf._doc.load_page(0)
        dpi = choose_pixmap_dpi(page)
    finally:
        pdf.close()
    # Allow ±2 DPI tolerance for rounding inside the bbox math.
    assert _DPI_200_LO <= dpi <= _DPI_200_HI, f"expected ~200, got {dpi}"


def test_high_dpi_image_clamps_to_cap(image_above_cap: Path) -> None:
    """Image computing >300 DPI → clamped to MAX_PIXMAP_DPI."""
    pdf = PDFFile(image_above_cap)
    try:
        page = pdf._doc.load_page(0)
        dpi = choose_pixmap_dpi(page)
    finally:
        pdf.close()
    assert dpi == MAX_PIXMAP_DPI


def test_negligible_image_filtered_out(negligible_image_only: Path) -> None:
    """Image below min_bbox_fraction → ignored, default wins."""
    pdf = PDFFile(negligible_image_only)
    try:
        page = pdf._doc.load_page(0)
        dpi = choose_pixmap_dpi(page)
    finally:
        pdf.close()
    assert dpi == DEFAULT_PIXMAP_DPI


def test_max_across_multiple_images(two_different_dpi_images: Path) -> None:
    """Page with two images at 100 DPI / 200 DPI native → 200 DPI wins."""
    pdf = PDFFile(two_different_dpi_images)
    try:
        page = pdf._doc.load_page(0)
        dpi = choose_pixmap_dpi(page)
    finally:
        pdf.close()
    assert _DPI_200_LO <= dpi <= _DPI_200_HI, f"expected ~200, got {dpi}"


def test_custom_default_overrides_floor(blank_page: Path) -> None:
    """``default=`` parameter sets the floor."""
    pdf = PDFFile(blank_page)
    try:
        page = pdf._doc.load_page(0)
        dpi = choose_pixmap_dpi(page, default=_OVERRIDE_DEFAULT_LOW)
    finally:
        pdf.close()
    assert dpi == _OVERRIDE_DEFAULT_LOW


def test_custom_cap_clamps(image_above_cap: Path) -> None:
    """``cap=`` parameter sets the ceiling."""
    pdf = PDFFile(image_above_cap)
    try:
        page = pdf._doc.load_page(0)
        dpi = choose_pixmap_dpi(page, cap=_OVERRIDE_CAP_LOW)
    finally:
        pdf.close()
    assert dpi == _OVERRIDE_CAP_LOW


# ── read_full_pixmap_jpeg with auto-DPI ───────────────────────────


def test_read_full_pixmap_auto_dpi_for_image_page(
    image_at_native_200_dpi: Path,
) -> None:
    """
    Auto-DPI on a multi-image page renders at the native resolution.

    The ``image_at_native_200_dpi`` fixture is single-image,
    full-coverage so it's image-dominant — the cheap path serves the
    embedded JPEG directly without ever touching the pixmap render.
    Confirm we get back image bytes.
    """
    pdf = PDFFile(image_at_native_200_dpi)
    try:
        blob, ext = pdf.read_full_pixmap_jpeg(0)
    finally:
        pdf.close()
    assert ext == "jpeg"
    assert blob[:3] == b"\xff\xd8\xff"


def test_read_full_pixmap_explicit_dpi_overrides_auto(
    vector_text_page: Path,
) -> None:
    """Passing ``dpi=72`` produces a smaller render than the default."""
    pdf = PDFFile(vector_text_page)
    try:
        small, _ = pdf.read_full_pixmap_jpeg(0, dpi=72)
        large, _ = pdf.read_full_pixmap_jpeg(0, dpi=300)
    finally:
        pdf.close()
    # 72 DPI render must be smaller than 300 DPI render of the same
    # vector page.
    assert len(small) < len(large)
    # Verify pixel dimensions scale ~as expected.
    small_img = Image.open(io.BytesIO(small))
    large_img = Image.open(io.BytesIO(large))
    assert small_img.size[0] < large_img.size[0]
    assert small_img.size[1] < large_img.size[1]


def test_read_full_pixmap_dpi_none_uses_auto(vector_text_page: Path) -> None:
    """``dpi=None`` (default) renders at DEFAULT_PIXMAP_DPI for image-less page."""
    pdf = PDFFile(vector_text_page)
    try:
        # Vector page → no image signal → DEFAULT_PIXMAP_DPI = 150.
        auto_blob, _ = pdf.read_full_pixmap_jpeg(0)
        explicit_blob, _ = pdf.read_full_pixmap_jpeg(0, dpi=DEFAULT_PIXMAP_DPI)
    finally:
        pdf.close()
    # Same DPI → same render. Output bytes may not be byte-equal due
    # to JPEG encoder timestamps, so compare decoded pixel dimensions.
    auto_img = Image.open(io.BytesIO(auto_blob))
    explicit_img = Image.open(io.BytesIO(explicit_blob))
    assert auto_img.size == explicit_img.size
