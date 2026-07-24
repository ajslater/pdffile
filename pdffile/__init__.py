"""Access PDFS with a ZipFile-like API."""

from __future__ import annotations

import math
from enum import Enum
from logging import Logger, getLogger
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from zipfile import ZipInfo

from filetype import guess
from pymupdf import Document, mupdf
from typing_extensions import Self

from pdffile._image_serve import (
    DEFAULT_PIXMAP_DPI,
    MAX_PIXMAP_DPI,
    PDF_FALLBACK_VERDICT,
    PageMode,
    PageVerdict,
    choose_pixmap_dpi,
    classify_page,
    extract_full_pixmap_jpeg,
    extract_image,
)
from pdffile.datetimes import to_datetime, to_pdf_date, to_zipinfo_timetuple

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

__all__ = (
    "DEFAULT_PIXMAP_DPI",
    "FALSY",
    "MAX_PIXMAP_DPI",
    "PDF_FALLBACK_VERDICT",
    "PDFFile",
    "PageFormat",
    "PageMode",
    "PageVerdict",
    "choose_pixmap_dpi",
)

FALSY: set[bool | str | None] = {None, "", "false", "0", False}
LOG: Logger = getLogger(__name__)


class PageFormat(Enum):
    """Read Format."""

    PDF = "pdf"
    IMAGE = "image"
    PIXMAP = "pixmap"
    #: Browser-renderable image when the page is image-dominant; falls
    #: through to ``PDF`` when the detector declines. Caller distinguishes
    #: the two by inspecting the ``ext`` written to ``props``.
    IMAGE_IF_DOMINANT = "image_if_dominant"
    #: Whole-page rasterization to RGB JPEG. Use when callers need an
    #: always-image response for any page (e.g. force-image override).
    PIXMAP_JPEG = "pixmap_jpeg"


class PDFFile:
    """ZipFile like API to PDFs."""

    MIME_TYPE: str = "application/pdf"
    SUFFIX: str = ".pdf"
    _TMP_SUFFIX: str = ".comicbox_tmp_pdf"
    _DEFAULT_PAGE_COUNT: int = 100
    _METADATA_PRESERVE_KEYS: tuple[str, ...] = (
        "format",
        "encryption",
        "creationDate",
        "modDate",
        "trapped",
    )

    @staticmethod
    def valid_pagenum(name: str) -> int:
        """Check if a string is a non-negative integeger."""
        page = int(name)
        if page < 0:
            reason = f"Negative page number {name} not valid."
            raise ValueError(reason)
        return page

    @staticmethod
    def to_datetime(pdf_date: str) -> datetime | None:
        """Convert a PDF date string to a datetime."""
        return to_datetime(pdf_date)

    @staticmethod
    def to_pdf_date(value: datetime | str) -> str | None:
        """Convert a datetime to a PDF date string."""
        return to_pdf_date(value)

    @staticmethod
    def to_bool(value: Any) -> bool:
        """Convert a boolean string to a python bool."""
        if isinstance(value, str):
            value = value.lower() not in FALSY
        return bool(value)

    @staticmethod
    def to_xml_bool(value: Any) -> str:
        """Convert a boolean value to an xml string."""
        if not isinstance(value, str):
            value = str(bool(value))
        return value.lower()

    _TYPE_CONVERSION_MAP = MappingProxyType(
        {
            "trapped": (to_bool, to_xml_bool),
            "creationDate": (to_datetime, to_pdf_date),
            "modDate": (to_datetime, to_pdf_date),
        }
    )

    @classmethod
    def is_pdffile(cls, path: str) -> bool:
        """Is the path a pdf."""
        if Path(path).suffix.lower() == cls.SUFFIX:
            return True
        kind = guess(path)
        return bool(kind and kind.mime == cls.MIME_TYPE)

    def __init__(self, path: Path) -> None:
        """Initialize document."""
        self._path: Path = path
        self._doc: Document = Document(self._path)

    def __enter__(self) -> Self:
        """Context enter."""
        return self

    def __exit__(self, *_args) -> None:
        """Context close."""
        self.close()

    def save(self) -> None:
        """Save PDF doc to disk."""
        tmp_path = self._path.with_suffix(self._TMP_SUFFIX)
        self._doc.save(
            tmp_path,
            garbage=4,
            deflate=True,
            deflate_images=True,
            deflate_fonts=True,
            encryption=mupdf.PDF_ENCRYPT_KEEP,
            use_objstms=True,
            pretty=True,
            no_new_id=True,
        )
        tmp_path.replace(self._path)

    def close(self) -> None:
        """Close the fitz doc."""
        if self._doc:
            if self._doc.is_dirty:
                self.save()
            self._doc.close()

    def pagelist(self) -> list[str]:
        """Zero padded page names."""
        page_count = self.get_page_count()
        zero_pad = math.floor(math.log10(page_count)) + 1
        return [f"{i:0{zero_pad}}" for i in range(page_count)]

    def namelist(self) -> list[str]:
        """Return sortable zero padded index strings."""
        emb_names = self._doc.embfile_names()
        page_names = self.pagelist()
        return emb_names + page_names

    def infolist(self) -> list[ZipInfo]:
        """Return ZipFile like infolist."""
        emb_infos = []
        doc_pdf_mod_date = (
            self._doc.metadata.get("modDate", "") if self._doc.metadata else ""
        )
        doc_mod_dttm_tuple = to_zipinfo_timetuple(doc_pdf_mod_date)

        for name in self._doc.embfile_names():
            pdf_info = self._doc.embfile_info(name)
            emb_pdf_mod_date = pdf_info.get("modDate", "")
            emb_size = pdf_info.get("size", 0)
            emb_mod_dttm_tuple = to_zipinfo_timetuple(emb_pdf_mod_date)
            info = ZipInfo(name, emb_mod_dttm_tuple)
            info.file_size = emb_size
            emb_infos.append(info)

        page_infos = [ZipInfo(name, doc_mod_dttm_tuple) for name in self.pagelist()]
        return emb_infos + page_infos

    def read_image(self, index: int) -> tuple[bytes, str]:
        """Read first image from page in original format."""
        first_image = self._doc.get_page_images(index, full=True)[0]
        xref = first_image[0]
        image_dict = self._doc.extract_image(xref)
        return image_dict["image"], image_dict["ext"]

    def read_pixmap(self, index: int) -> tuple[bytes, str]:
        """Convert page to pixmap."""
        pix = self._doc.get_page_pixmap(index)
        output = "ppm"
        return pix.tobytes(output=output), output

    def classify_page(self, index: int) -> PageVerdict:
        """
        Decide how page ``index`` should be served.

        Returns a :class:`PageVerdict`. ``PageMode.PDF_FALLBACK``
        means the caller should use the regular PDF path; the other
        modes mean the page is image-dominant and can be served as
        raw image bytes via :meth:`read_image_if_dominant`.

        Cheap — runs on parsed PDF metadata, single-digit milliseconds
        per page even on text-heavy documents.
        """
        return classify_page(self._doc, index)

    def read_image_if_dominant(self, index: int) -> tuple[bytes, str] | None:
        """
        Return ``(bytes, ext)`` if page is image-dominant, else ``None``.

        ``ext`` is the embedded image's encoding ('jpeg', 'png',
        'webp') for ``IMAGE_DIRECT`` verdicts, or 'jpeg' for
        ``IMAGE_TRANSCODE`` verdicts (CMYK / JBIG2 images re-encoded
        via Pixmap; rotated pages re-rendered via the page pixmap,
        which applies /Rotate).

        ``None`` means the caller should use :meth:`read_pdf` (or
        another fallback path) — the page has vector content that
        would be lost in a raw-image serve.
        """
        verdict = self.classify_page(index)
        if verdict.mode is PageMode.PDF_FALLBACK:
            return None
        return extract_image(self._doc, verdict)

    def read_full_pixmap_jpeg(
        self, index: int, *, dpi: int | None = None
    ) -> tuple[bytes, str]:
        """
        Render the whole page to RGB JPEG.

        Faster than :meth:`read_pixmap` for browser callers (PPM is
        not browser-renderable; PIL would need to be in the loop to
        transcode). Tries the cheap embedded-image path first when
        the page happens to be image-dominant.

        ``dpi=None`` (default) auto-picks a render DPI from the page's
        embedded-image resolution via :func:`choose_pixmap_dpi`; pages
        with no images render at :data:`DEFAULT_PIXMAP_DPI`. Pass an
        integer to override. The auto path doesn't apply when the
        cheap embedded-image branch fires — those return the embedded
        image at its native resolution regardless.

        Always succeeds for valid pages — raises if PyMuPDF can't
        render the page at all.
        """
        cheap = self.read_image_if_dominant(index)
        if cheap is not None:
            return cheap
        result = extract_full_pixmap_jpeg(self._doc, index, dpi=dpi)
        if result is None:
            reason = f"pdffile full pixmap render failed for page {index}"
            raise RuntimeError(reason)
        return result

    def read_pdf(self, index: int) -> tuple[bytes, str]:
        """
        Read a pdf page as a complete one-page pdf.

        Uses ``insert_pdf`` rather than ``Document.convert_to_pdf``:
        the latter rebuilds the page's content stream and during that
        rebuild it drops text rendering mode operators (notably ``3 Tr``,
        invisible text) and renames specialised OCR fonts like
        ``HiddenHorzOCR`` to ordinary text fonts. The net effect on
        Acrobat-OCR'd PDFs is that the invisible OCR overlay turns
        visible — text "doubles up" against the page's raster under any
        renderer that follows the spec (PDF.js, MuPDF itself).
        ``insert_pdf`` copies the page faithfully — same operators,
        same fonts, no warnings, pixel-identical render to the source.
        """
        out = Document()
        out.insert_pdf(self._doc, from_page=index, to_page=index)
        # ``no_new_id=True`` keeps output deterministic across calls; without
        # it pymupdf stamps a fresh random ``/ID`` array on every save and
        # downstream byte-equality fixtures churn on every test run.
        return out.tobytes(no_new_id=True), "pdf"

    def read_embedded_file(self, filename: str) -> tuple[bytes, str]:
        """Read embedded file."""
        return self._doc.embfile_get(filename), Path(filename).suffix[:1]

    def read(self, filename: str, fmt: str = "", props: dict | None = None) -> bytes:
        """
        Return a single page pdf doc, image or pixmap or embedded file.

        If a props dict is passed in, the read file extension is
        written to the ``ext`` key. For ``IMAGE_IF_DOMINANT`` callers
        inspect ``ext`` to distinguish a successful image serve
        (``jpeg``/``png``/``webp``) from the PDF fall-through
        (``pdf``).
        """
        try:
            if not fmt:
                fmt = PageFormat.PDF.value
            index = self.valid_pagenum(filename)
            if fmt == PageFormat.IMAGE.value:
                try:
                    page_bytes, ext = self.read_image(index)
                except Exception as exc:
                    LOG.warning(
                        f"Unable to extract first image from page, converting to pixmap: {exc}"
                    )
                    page_bytes, ext = self.read_pixmap(index)
            elif fmt == PageFormat.PIXMAP.value:
                page_bytes, ext = self.read_pixmap(index)
            elif fmt == PageFormat.IMAGE_IF_DOMINANT.value:
                served = self.read_image_if_dominant(index)
                if served is not None:
                    page_bytes, ext = served
                else:
                    page_bytes, ext = self.read_pdf(index)
            elif fmt == PageFormat.PIXMAP_JPEG.value:
                page_bytes, ext = self.read_full_pixmap_jpeg(index)
            else:
                page_bytes, ext = self.read_pdf(index)
        except ValueError:
            page_bytes, ext = self.read_embedded_file(filename)
        if props is not None:
            props["ext"] = ext
        return page_bytes

    def get_page_count(self) -> int:
        """Get the page count from the doc or the default highnum."""
        try:
            page_count = self._doc.page_count
        except Exception as exc:
            LOG.warning(f"Error reading page count for {self._path}: {exc}")
            page_count = self._DEFAULT_PAGE_COUNT
        return page_count

    @classmethod
    def _convert_metadata(cls, metadata: dict, *, to: bool) -> dict:
        """MuPDF only writes booleans as strings."""
        converted_metadata = {}
        func_index = 0 if to else 1
        for key, functions in cls._TYPE_CONVERSION_MAP.items():
            value = metadata.get(key)
            if value is not None:
                func = functions[func_index]
                converted_metadata[key] = func(value)
        metadata.update(converted_metadata)
        return metadata

    def get_metadata(self) -> dict:
        """Return metadata from the pdf doc."""
        md = self._doc.metadata
        if not md:
            md = {}
        return self._convert_metadata(md, to=True)

    def _get_preserved_metadata(self) -> dict:
        """Get preserved metadata."""
        old_metadata = {}
        if self._doc.metadata:
            for key in self._METADATA_PRESERVE_KEYS:
                if value := self._doc.metadata.get(key):
                    old_metadata[key] = value
        return old_metadata

    def write_metadata(self, metadata: Mapping) -> None:
        """Set metadata to the pdf doc."""
        preserved_metadata = self._get_preserved_metadata()
        new_metadata = {**preserved_metadata, **metadata}
        converted_metadata = self._convert_metadata(new_metadata, to=False)
        self._doc.set_metadata(converted_metadata)

    def remove(self, name: str) -> None:
        """Remove files or pages from the pdf."""
        try:
            page = self.valid_pagenum(name)
            self._doc.delete_page(page)
        except ValueError:
            self._doc.embfile_del(name)

    def writestr(
        self, name: str, buffer: str | bytes | bytearray | memoryview[int], **_kwargs
    ) -> None:
        """
        Write string to an embedded file.

        Accept compress_type & compress args but discard them.
        """
        try:
            _ = self.valid_pagenum(name)
            reason = "Writing PDF pages not implemented."
            raise NotImplementedError(reason)
        except ValueError:
            if isinstance(buffer, str):
                buffer = buffer.encode(errors="replace")
            self._doc.embfile_add(name, buffer)

    def repack(self) -> None:
        """Noop. For compatibility with zipfile-patch."""
