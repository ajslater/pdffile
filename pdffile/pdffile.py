"""Access PDFS with a ZipFile-like API."""

from __future__ import annotations

import math
from datetime import datetime
from logging import getLogger
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from zipfile import ZipInfo

import fitz
from dateutil import parser
from filetype import guess

if TYPE_CHECKING:
    from collections.abc import Mapping


PDF_DATETIME_TEMPLATE = "D:%Y%m%d%H%M%S%z"
TZ_DELIMITERS = ("+", "-")
FALSY = {None, "", "false", "0", False}
LOG = getLogger(__name__)


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
    def to_datetime(pdf_date: str) -> datetime | None:
        """Convert a PDF date string to a datetime."""
        if not pdf_date or not pdf_date.startswith("D:"):
            return None
        dt_str = pdf_date.replace("'", "")
        return datetime.strptime(dt_str, PDF_DATETIME_TEMPLATE)  # noqa: DTZ007

    @staticmethod
    def to_pdf_date(value: datetime | str) -> str | None:
        """Convert a datetime to a PDF date string."""
        if not value:
            return None

        if isinstance(value, str):
            if value.startswith("D:"):
                return value
            dt = parser.parse(value)
        else:
            dt = value

        dt_str = dt.strftime(PDF_DATETIME_TEMPLATE)

        # Separate timezone and convert to PDF offset string
        for delimiter in TZ_DELIMITERS:
            parts = dt_str.split(delimiter)
            if len(parts) > 1:
                dt_str, tz_str = parts
                h = tz_str[:2]
                m = tz_str[2:4]
                break
        else:
            # Default
            delimiter = "+"
            h = m = "00"
        offset_str = f"{h}'{m}'"

        # Recombine with PDF offset str.
        return f"{dt_str}{delimiter}{offset_str}"

    @staticmethod
    def to_bool(value: Any) -> bool:
        """Convert a boolean string to a python bool."""
        if isinstance(str, value):
            value = value.lower() not in FALSY
        return bool(value)

    @staticmethod
    def to_xml_bool(value: Any) -> str:
        """Convert a boolean value to an xml string."""
        if not isinstance(value, str):
            value = str(bool(value))
        return value.lower()

    _TYPE_COVERSION_MAP = MappingProxyType(
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
        self._doc: fitz.Document = fitz.Document(self._path)

    def __enter__(self):
        """Context enter."""
        return self

    def __exit__(self, *_args) -> None:
        """Context close."""
        self.close()

    def namelist(self) -> list[str]:
        """Return sortable zero padded index strings."""
        page_count = self.get_page_count()
        zero_pad = math.floor(math.log10(page_count)) + 1
        return [f"{i:0{zero_pad}}" for i in range(page_count)]

    def infolist(self) -> list[ZipInfo]:
        """Return ZipFile like infolist."""
        infos = []
        for index in self.namelist():
            info = ZipInfo(index)
            infos.append(info)
        return infos

    def read(self, filename: str, to_pixmap: bool = False) -> bytes:  # noqa: FBT002
        """Return a single page pdf doc or pixmap."""
        index = int(filename)

        if to_pixmap:
            pix = self._doc.get_page_pixmap(index)  # type: ignore[reportAttributeAccessIssue]
            page_bytes = pix.tobytes(output="ppm")
        else:
            page_bytes = self._doc.convert_to_pdf(index, index)
        return page_bytes

    def close(self) -> None:
        """Close the fitz doc."""
        if self._doc:
            self._doc.close()

    def get_page_count(self) -> int:
        """Get the page count from the doc or the default highnum."""
        try:
            page_count = self._doc.page_count
        except Exception as exc:
            LOG.warning(f"Error reading page count for {self._path}: {exc}")
            page_count = self._DEFAULT_PAGE_COUNT
        return page_count

    @classmethod
    def _converted_metadata(cls, metadata: Mapping, to: bool) -> dict:
        """MuPDF only writes booleans as strings."""
        converted_metadata = {}
        func_index = 0 if to else 1
        for key, functions in cls._TYPE_COVERSION_MAP.items():
            value = metadata.get(key)
            if value is not None:
                func = functions[func_index]
                converted_metadata[key] = func(value)
        return converted_metadata

    def get_metadata(self) -> dict:
        """Return metadata from the pdf doc."""
        md = self._doc.metadata
        if not md:
            md = {}
        converted_metadata = self._converted_metadata(md, to=True)
        md.update(converted_metadata)
        return md

    def _get_preserved_metadata(self) -> dict:
        """Get preserved metadata."""
        old_metadata = {}
        if self._doc.metadata:
            for key in self._METADATA_PRESERVE_KEYS:
                if value := self._doc.metadata.get(key):
                    old_metadata[key] = value
        return old_metadata

    def save_metadata(self, metadata: Mapping) -> None:
        """Set metadata to the pdf doc."""
        preserved_metadata = self._get_preserved_metadata()
        converted_metadata = self._converted_metadata(metadata, to=False)
        new_metadata = {**preserved_metadata, **metadata, **converted_metadata}
        self._doc.set_metadata(new_metadata)  # type: ignore[reportAttributeAccessIssue]

        tmp_path = self._path.with_suffix(self._TMP_SUFFIX)
        self._doc.save(
            tmp_path,
            garbage=4,
            deflate=True,
            deflate_images=True,
            deflate_fonts=True,
            encryption=fitz.PDF_ENCRYPT_KEEP,  # type: ignore[reportAttributeAccessIssue]
            linear=True,
            pretty=True,
            no_new_id=True,
        )
        tmp_path.replace(self._path)
