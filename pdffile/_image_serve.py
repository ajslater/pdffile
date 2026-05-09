"""
Image-dominant page detection + browser-safe extraction.

Most "comic PDFs" are scanned-image wrappers — one full-bleed JPEG or
PNG per page with no real vector content. Callers (Codex, OPDS readers)
can serve those pages as raw image bytes so the browser renders them
in a plain ``<img>`` instead of going through pdf.js on the client.

This module provides:

* :class:`PageMode`, :class:`PageVerdict` — classification result types.
* :func:`classify_page` — fast detector returning a verdict per page.
* :func:`extract_image` — turn a verdict into ``(bytes, ext)``.
* :func:`extract_full_pixmap_jpeg` — render a page to RGB JPEG when
  the verdict declined (e.g. forced ``image`` mode on a vector page).

Detection runs on parsed PDF metadata — no rasterization — so it
costs single-digit milliseconds per page.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from logging import getLogger
from typing import Final

import pymupdf

LOG = getLogger(__name__)


# ── Tunables ──────────────────────────────────────────────────────

#: Combined image bbox area must cover at least this fraction of the
#: page rect for the page to be considered image-dominant. Tightens
#: against pages that have a small inset image surrounded by margin
#: white-space (book title pages, chapter intros).
MIN_COVERAGE: Final[float] = 0.85

#: Visible text length above which the page is treated as having
#: meaningful vector content. Small OCR scraps under this bar are
#: tolerated.
MAX_TEXT_CHARS: Final[int] = 50

#: Image-dominant verdict requires exactly this many embedded images.
#: Multi-image pages fall through to the PDF path which composites
#: them correctly.
EXACT_IMAGE_COUNT: Final[int] = 1

#: Browser-native image extensions we can serve as-stored.
BROWSER_NATIVE_EXTS: Final[frozenset[str]] = frozenset({"jpeg", "jpg", "png", "webp"})

#: Browser-safe colorspace channel counts (1 = Gray, 3 = RGB).
#: CMYK (4) and exotic colorspaces require a transcode.
BROWSER_NATIVE_COLORSPACES: Final[frozenset[int]] = frozenset({1, 3})

#: Default DPI when no embedded image gives us a native-resolution
#: signal (pure vector text pages, etc). 150 DPI matches the bottom
#: of the typical CBZ resolution range and renders sharp on most
#: displays without producing wasteful file sizes.
DEFAULT_PIXMAP_DPI: Final[int] = 150

#: Hard upper bound on auto-detected DPI. Without this, a single tiny
#: high-DPI logo on a page can demand a multi-thousand-pixel render.
#: Past 300 DPI browsers can't show the detail and file sizes get
#: actively bad on mobile.
MAX_PIXMAP_DPI: Final[int] = 300

#: Embedded images smaller than this fraction of the page rect are
#: ignored when computing native DPI. Filters out 1-px tracking
#: pixels and decorative dots that would otherwise drag the
#: measurement around.
MIN_DPI_BBOX_FRACTION: Final[float] = 0.001


# ── Public types ──────────────────────────────────────────────────


class PageMode(Enum):
    """How a page should be served."""

    #: Embedded image bytes are browser-renderable as-stored.
    IMAGE_DIRECT = "image_direct"
    #: Embedded image needs re-encoding (CMYK, JBIG2, JPEG2000,
    #: rotated, etc.) to RGB JPEG via Pixmap before serving.
    IMAGE_TRANSCODE = "image_transcode"
    #: Page has vector content; serve it through the PDF path.
    PDF_FALLBACK = "pdf_fallback"


@dataclass(frozen=True, slots=True)
class PageVerdict:
    """One page's classification."""

    mode: PageMode
    image_xref: int | None
    ext: str | None  # original encoding when known


PDF_FALLBACK_VERDICT: Final[PageVerdict] = PageVerdict(
    mode=PageMode.PDF_FALLBACK, image_xref=None, ext=None
)


# ── Detection helpers ─────────────────────────────────────────────


def _coverage_for(page: pymupdf.Page, image: tuple) -> float | None:
    """Return image coverage of ``page`` in [0, 1], or None on failure."""
    page_area = page.rect.width * page.rect.height
    if not page_area:
        return None
    try:
        # ``transform=False`` (default) returns a Rect; pyright's
        # stub picks the (Rect, Matrix) overload and mis-narrows.
        bbox: pymupdf.Rect = page.get_image_bbox(image)  # pyright: ignore[reportAssignmentType]
    except Exception as exc:
        LOG.warning(f"pdffile classify get_image_bbox failed: {exc}")
        return None
    if bbox.is_empty:
        return None
    return min((bbox.width * bbox.height) / page_area, 1.0)


def _passes_image_gates(page: pymupdf.Page, images: list) -> bool:
    """Run the image-dominant gates on a page; True iff they all pass."""
    if len(images) != EXACT_IMAGE_COUNT:
        return False
    coverage = _coverage_for(page, images[0])
    if coverage is None or coverage < MIN_COVERAGE:
        return False
    # ``get_text("text")`` returns str; pyright stub picks the
    # widest union (str | dict | list) and can't narrow.
    text: str = page.get_text("text")  # pyright: ignore[reportAssignmentType]
    if len(text.strip()) > MAX_TEXT_CHARS:
        return False
    return not page.get_drawings()  # annotations / form fields show up here


def _verdict_for_image(
    doc: pymupdf.Document, xref: int, *, rotated: bool
) -> PageVerdict:
    """
    Decide IMAGE_DIRECT vs IMAGE_TRANSCODE for an image-dominant page.

    Rotated pages always need transcoding (extracted bytes don't carry
    rotation; the Pixmap path applies it). Non-browser-native formats
    (JBIG2, JPEG 2000, CCITT) and CMYK colorspace also need transcode.
    """
    if rotated:
        return PageVerdict(PageMode.IMAGE_TRANSCODE, xref, None)
    try:
        info = doc.extract_image(xref)
    except Exception as exc:
        LOG.warning(f"pdffile classify extract_image({xref}) failed: {exc}")
        return PDF_FALLBACK_VERDICT
    ext = (info.get("ext") or "").lower()
    cs = info.get("colorspace", 0)
    if ext in BROWSER_NATIVE_EXTS and cs in BROWSER_NATIVE_COLORSPACES:
        return PageVerdict(PageMode.IMAGE_DIRECT, xref, ext)
    return PageVerdict(PageMode.IMAGE_TRANSCODE, xref, ext)


# ── Detection (public) ────────────────────────────────────────────


def classify_page(doc: pymupdf.Document, index: int) -> PageVerdict:
    """
    Return how page ``index`` should be served.

    All checks operate on parsed PDF metadata — no rasterization —
    so the detector runs in single-digit milliseconds even on
    text-heavy pages.

    Returns ``PDF_FALLBACK_VERDICT`` for any page that should go
    through the regular PDF path: multi-image pages, mostly-margin
    pages, pages with significant vector text or drawings, pages
    whose embedded image fails to extract.
    """
    try:
        page = doc.load_page(index)
    except Exception as exc:
        LOG.warning(f"pdffile classify load_page({index}) failed: {exc}")
        return PDF_FALLBACK_VERDICT
    images = page.get_images(full=True)
    if not _passes_image_gates(page, images):
        return PDF_FALLBACK_VERDICT
    return _verdict_for_image(doc, images[0][0], rotated=bool(page.rotation))


# ── Extraction (public) ───────────────────────────────────────────


def _extract_direct(
    doc: pymupdf.Document, xref: int, ext: str | None
) -> tuple[bytes, str] | None:
    """Return (bytes, ext) for an as-stored image, or None on failure."""
    try:
        info = doc.extract_image(xref)
    except Exception as exc:
        LOG.warning(f"pdffile extract_direct xref={xref} failed: {exc}")
        return None
    blob = info.get("image")
    if not blob:
        return None
    actual_ext = (info.get("ext") or ext or "jpeg").lower()
    if actual_ext == "jpg":
        actual_ext = "jpeg"
    return blob, actual_ext


def _extract_transcode(doc: pymupdf.Document, xref: int) -> tuple[bytes, str] | None:
    """
    Re-encode an embedded image to RGB JPEG.

    Used for CMYK colorspaces, JBIG2 / JPEG 2000 / CCITT formats, and
    rotated pages — anything browsers don't render natively.
    """
    try:
        pix = pymupdf.Pixmap(doc, xref)
        if pix.colorspace and pix.colorspace.n not in BROWSER_NATIVE_COLORSPACES:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        blob = pix.tobytes("jpeg")
    except Exception as exc:
        LOG.warning(f"pdffile transcode xref={xref} failed: {exc}")
        return None
    if not blob:
        return None
    return blob, "jpeg"


def extract_image(
    doc: pymupdf.Document, verdict: PageVerdict
) -> tuple[bytes, str] | None:
    """Return (bytes, ext) per the verdict, or None on failure."""
    if verdict.mode is PageMode.IMAGE_DIRECT and verdict.image_xref is not None:
        return _extract_direct(doc, verdict.image_xref, verdict.ext)
    if verdict.mode is PageMode.IMAGE_TRANSCODE and verdict.image_xref is not None:
        return _extract_transcode(doc, verdict.image_xref)
    return None


def choose_pixmap_dpi(
    page: pymupdf.Page,
    *,
    default: int = DEFAULT_PIXMAP_DPI,
    cap: int = MAX_PIXMAP_DPI,
    min_bbox_fraction: float = MIN_DPI_BBOX_FRACTION,
) -> int:
    """
    Pick a render DPI matching the page's embedded-image resolution.

    Walks the page's images and computes each one's *native* placed
    DPI from its pixel dimensions and bbox. Returns the highest value
    seen across non-negligible images, clamped to ``[default, cap]``.
    Pages with no images (pure vector text) return ``default``.

    The cap exists because a single tiny high-DPI logo on a large
    page would otherwise demand a multi-thousand-pixel render. The
    bbox-fraction filter ignores 1-px tracking pixels and decorative
    dots that would distort the measurement.
    """
    page_area = page.rect.width * page.rect.height
    if not page_area:
        return default
    best = default
    for img in page.get_images(full=True):
        img_w, img_h = img[2], img[3]
        if not img_w or not img_h:
            continue
        try:
            # ``transform=False`` (default) returns a Rect; pyright's
            # stub picks the (Rect, Matrix) overload and mis-narrows.
            bbox: pymupdf.Rect = page.get_image_bbox(img)  # pyright: ignore[reportAssignmentType]
        except Exception as exc:
            LOG.debug(f"pdffile choose_pixmap_dpi get_image_bbox failed: {exc}")
            continue
        if bbox.is_empty:
            continue
        if (bbox.width * bbox.height) / page_area < min_bbox_fraction:
            continue
        bbox_w_in = bbox.width / 72
        bbox_h_in = bbox.height / 72
        if bbox_w_in <= 0 or bbox_h_in <= 0:
            continue
        dpi = max(img_w / bbox_w_in, img_h / bbox_h_in)
        best = max(best, round(dpi))
    return min(best, cap)


def extract_full_pixmap_jpeg(
    doc: pymupdf.Document, index: int, *, dpi: int | None = None
) -> tuple[bytes, str] | None:
    """
    Render a whole page to RGB JPEG via Pixmap.

    Used when the caller forces image rendering on a page that isn't
    image-dominant — composites text, vector ink, and multiple images
    correctly. Slower than the per-image extraction paths.

    ``dpi=None`` (default) picks a render DPI from the page's
    embedded-image resolution (see :func:`choose_pixmap_dpi`); pages
    with no images render at :data:`DEFAULT_PIXMAP_DPI`. Pass an
    integer to override.
    """
    try:
        page = doc.load_page(index)
        chosen_dpi = dpi if dpi is not None else choose_pixmap_dpi(page)
        zoom = chosen_dpi / 72.0
        matrix = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix)
        if pix.colorspace and pix.colorspace.n not in BROWSER_NATIVE_COLORSPACES:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        blob = pix.tobytes("jpeg")
    except Exception as exc:
        LOG.warning(f"pdffile full pixmap page={index} failed: {exc}")
        return None
    if not blob:
        return None
    return blob, "jpeg"
