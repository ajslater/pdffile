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

import math
from dataclasses import dataclass
from enum import Enum
from logging import getLogger
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

import pymupdf

if TYPE_CHECKING:
    from collections.abc import Mapping

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
    page_index: int | None = None
    #: Display rotation in degrees — the page's /Rotate combined with
    #: the content-stream placement rotation. Nonzero forces a whole-
    #: page render at extraction time (as-stored bytes can't carry it).
    rotation: int = 0


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


#: Placement rotation by the sign pattern of the transform matrix's
#: ``(a, b, c, d)``. The 90/270 patterns are pymupdf-empirical (see
#: tests); they only need to be stable, not "right" — callers
#: page-render for any nonzero rotation, so a swapped label still
#: displays correctly. Patterns absent here (mirrored, skewed) map to
#: ``None`` via ``.get``.
_ROTATION_BY_SIGNS: Final[Mapping[tuple[int, int, int, int], int]] = MappingProxyType(
    {
        (1, 0, 0, 1): 0,
        (-1, 0, 0, -1): 180,
        (0, -1, 1, 0): 90,
        (0, 1, -1, 0): 270,
    }
)


def _sign(value: float, tol: float) -> int:
    """Ternary sign of ``value``, treating ``[-tol, tol]`` as zero."""
    return (value > tol) - (value < -tol)


def _placement_rotation(page: pymupdf.Page, image: tuple) -> int | None:
    """
    Degrees the content stream rotates the image's placement.

    Returns 0/90/180/270 for axis-aligned placements, or ``None`` for
    mirrored, skewed, or degenerate matrices — those can only be
    reproduced by the PDF path. Excludes the page's /Rotate, which
    pymupdf reports separately via ``page.rotation`` (the transform
    from ``get_image_bbox`` is in unrotated page space).
    """
    try:
        _, matrix = page.get_image_bbox(image, transform=True)
    except Exception as exc:
        LOG.warning(f"pdffile classify placement transform failed: {exc}")
        return None
    a, b, c, d = matrix.a, matrix.b, matrix.c, matrix.d
    scale = max(abs(a), abs(b), abs(c), abs(d))
    if not scale:
        return None
    tol = scale * 1e-4
    signs = (_sign(a, tol), _sign(b, tol), _sign(c, tol), _sign(d, tol))
    return _ROTATION_BY_SIGNS.get(signs)


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
    doc: pymupdf.Document, index: int, xref: int, *, rotation: int
) -> PageVerdict:
    """
    Decide IMAGE_DIRECT vs IMAGE_TRANSCODE for an image-dominant page.

    ``rotation`` is the page's *display* rotation (/Rotate combined
    with the content-stream placement). Rotated pages always need
    transcoding: extracted bytes don't carry rotation, so
    ``extract_image`` re-renders the whole page (which applies it)
    instead of decoding the bare xref. Non-browser-native formats
    (JBIG2, JPEG 2000, CCITT) and CMYK colorspace also need transcode,
    via the cheaper xref decode.
    """
    if rotation:
        return PageVerdict(
            PageMode.IMAGE_TRANSCODE, xref, None, page_index=index, rotation=rotation
        )
    try:
        info = doc.extract_image(xref)
    except Exception as exc:
        LOG.warning(f"pdffile classify extract_image({xref}) failed: {exc}")
        return PDF_FALLBACK_VERDICT
    ext = (info.get("ext") or "").lower()
    cs = info.get("colorspace", 0)
    if ext in BROWSER_NATIVE_EXTS and cs in BROWSER_NATIVE_COLORSPACES:
        return PageVerdict(PageMode.IMAGE_DIRECT, xref, ext, page_index=index)
    return PageVerdict(PageMode.IMAGE_TRANSCODE, xref, ext, page_index=index)


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
    placement = _placement_rotation(page, images[0])
    if placement is None:
        # Mirrored / skewed placement — only the PDF path renders it.
        return PDF_FALLBACK_VERDICT
    display_rotation = (page.rotation + placement) % 360
    if placement and not display_rotation:
        # /Rotate and the placement nominally cancel; serving as-stored
        # would bet on the two sign conventions matching exactly, so
        # take the always-correct PDF path instead.
        return PDF_FALLBACK_VERDICT
    return _verdict_for_image(doc, index, images[0][0], rotation=display_rotation)


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
    Re-encode an embedded image to RGB JPEG, as-stored.

    Used for CMYK colorspaces and JBIG2 / JPEG 2000 / CCITT formats —
    encodings browsers don't render natively. Decodes the bare xref,
    so page geometry (/Rotate, CTM) is NOT applied — rotated pages
    must go through :func:`extract_full_pixmap_jpeg` instead.
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
        if verdict.rotation and verdict.page_index is not None:
            # A bare xref decode can't carry the page's /Rotate —
            # render the whole page, which applies it.
            return extract_full_pixmap_jpeg(doc, verdict.page_index)
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
            bbox, matrix = page.get_image_bbox(img, transform=True)
        except Exception as exc:
            LOG.debug(f"pdffile choose_pixmap_dpi get_image_bbox failed: {exc}")
            continue
        if bbox.is_empty:
            continue
        if (bbox.width * bbox.height) / page_area < min_bbox_fraction:
            continue
        # The transform's columns are the placed spans of the image's
        # own x and y axes, so each pixel dimension pairs with the
        # right physical extent even for CTM-rotated placements (a
        # naive bbox-width / image-width pairing mixes the axes for
        # 90/270 placements and inflates the DPI by the aspect ratio).
        span_x_in = math.hypot(matrix.a, matrix.b) / 72
        span_y_in = math.hypot(matrix.c, matrix.d) / 72
        if span_x_in <= 0 or span_y_in <= 0:
            continue
        dpi = max(img_w / span_x_in, img_h / span_y_in)
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
