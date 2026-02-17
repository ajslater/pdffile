"""Access PDFS with a ZipFile-like API."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum
from logging import Logger, getLogger
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from zipfile import ZipInfo

from dateutil import parser
from filetype import guess
from pymupdf import Document, mupdf
from typing_extensions import Self

if TYPE_CHECKING:
    from collections.abc import Mapping

PDF_DATE_PREFIX = "D:"
DATETIME_AWARE_TMPL = "D:%Y%m%d%H%M%S%z"
DATETIME_NAIVE_TMPL = "D:%Y%m%d%H%M%S"
DATE_TMPL = "D:%Y%m%d"
DATETIME_TEMPLATES: tuple[str, ...] = (
    DATETIME_AWARE_TMPL,
    DATETIME_NAIVE_TMPL,
    DATE_TMPL,
)
DEFAULT_DTTM_TUPLE: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0)
TZ_DELIMITERS = ("+", "-")
FALSY: set[None | bool | str] = {None, "", "false", "0", False}
LOG: Logger = getLogger(__name__)


class PageFormat(Enum):
    """Read Format."""

    PDF = "pdf"
    IMAGE = "image"
    PIXMAP = "pixmap"


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
        if isinstance(pdf_date, datetime):
            return pdf_date
        if not pdf_date or not pdf_date.startswith(PDF_DATE_PREFIX):
            return None
        dt_str = pdf_date.replace("'", "")
        dt_str = dt_str.replace("Z", "+")
        last_exc = None
        dttm = None
        for template in DATETIME_TEMPLATES:
            try:
                dttm = datetime.strptime(dt_str, template)  # noqa: DTZ007
                if not dttm.tzinfo:
                    dttm.replace(tzinfo=timezone.utc)
                break
            except ValueError as exc:
                last_exc = exc
        if not dttm:
            if last_exc:
                raise last_exc
            reason = "Unable to parse pdf datetime {pdf_date}."
            raise ValueError(reason)
        return dttm

    @classmethod
    def _pdf_date_to_zipinfo_dttm_tuple(
        cls, pdf_date: str
    ) -> tuple[int, int, int, int, int, int]:
        if pdf_date and (dttm := cls.to_datetime(pdf_date)):
            dttm_tuple = dttm.timetuple()[:6]
        else:
            dttm_tuple = DEFAULT_DTTM_TUPLE
        return dttm_tuple

    @staticmethod
    def to_pdf_date(value: datetime | str) -> str | None:
        """Convert a datetime to a PDF date string."""
        if not value:
            return None

        if isinstance(value, str):
            if value.startswith(PDF_DATE_PREFIX):
                return value
            dttm = parser.parse(value)
        else:
            dttm = value

        if not dttm.tzinfo:
            dttm.replace(tzinfo=timezone.utc)

        dttm_str = dttm.strftime(DATETIME_AWARE_TMPL)

        # Separate timezone and convert to PDF offset string
        for delimiter in TZ_DELIMITERS:
            parts = dttm_str.split(delimiter)
            if len(parts) > 1:
                dttm_str, tz_str = parts
                h = tz_str[:2]
                m = tz_str[2:4]
                break
        else:
            # Default
            delimiter = "+"
            h = m = "00"
        offset_str = f"{h}'{m}'"

        # Recombine with PDF offset str.
        return f"{dttm_str}{delimiter}{offset_str}"

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
        doc_mod_dttm_tuple = self._pdf_date_to_zipinfo_dttm_tuple(doc_pdf_mod_date)

        for name in self._doc.embfile_names():
            pdf_info = self._doc.embfile_info(name)
            emb_pdf_mod_date = pdf_info.get("modDate", "")
            emb_size = pdf_info.get("size", 0)
            emb_mod_dttm_tuple = self._pdf_date_to_zipinfo_dttm_tuple(emb_pdf_mod_date)
            info = ZipInfo(name, emb_mod_dttm_tuple)
            info.file_size = emb_size
            emb_infos.append(info)

        page_infos = [ZipInfo(name, doc_mod_dttm_tuple) for name in self.pagelist()]
        return emb_infos + page_infos

    def read_image(self, index: int):
        """Read first image from page in original format."""
        first_image = self._doc.get_page_images(index, full=True)[0]
        xref = first_image[0]
        image_dict = self._doc.extract_image(xref)
        return image_dict["image"], image_dict["ext"]

    def read_pixmap(self, index: int):
        """Convert page to pixmap."""
        pix = self._doc.get_page_pixmap(index)
        return pix.tobytes(output="ppm"), "ppm"

    def read_pdf(self, index: int):
        """Read a pdf page as complete one page pdf."""
        return self._doc.convert_to_pdf(index, index), "pdf"

    def read_embedded_file(self, filename: str):
        """Read embedded file."""
        return self._doc.embfile_get(filename), Path(filename).suffix[:1]

    def read(self, filename: str, fmt: str = "", props: dict | None = None) -> bytes:
        """
        Return a single page pdf doc, image or pixmap or embedded file.

        If a props dict is passed in, the read file extension is written it on the 'ext' key.
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
