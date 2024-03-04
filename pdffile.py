"""Access PDFS with a ZipFile-like API."""

from __future__ import annotations

import math
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import ZipInfo

import fitz
from filetype import guess

if TYPE_CHECKING:
    from collections.abc import Mapping

LOG = getLogger(__name__)


class PDFFile:
    """ZipFile like API to PDFs."""

    MIME_TYPE: str = "application/pdf"
    SUFFIX: str = ".pdf"
    _TMP_SUFFIX: str = ".comicbox_tmp_pdf"
    _DEFAULT_PAGE_COUNT: int = 100
    _METADATA_COPY_KEYS: tuple[str, ...] = (
        "format",
        "encryption",
        "creationDate",
        "modDate",
        "trapped",
    )

    @classmethod
    def is_pdffile(cls, path: str) -> bool:
        """Is the path a pdf."""
        if Path(path).suffix.lower() == cls.SUFFIX:
            return True
        kind = guess(path)  # type: ignore
        return bool(kind and kind.mime == cls.MIME_TYPE)

    def __init__(self, path: Path) -> None:
        """Initialize document."""
        self._path: Path = path
        self._doc: fitz.Document = fitz.Document(self._path)  # type: ignore

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

    def read(self, filename: str, to_pixmap: bool = False) -> bytes:
        """Return a single page pdf doc or pixmap."""
        index = int(filename)

        if to_pixmap:
            pix = self._doc.get_page_pixmap(index)  # type: ignore
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

    def get_metadata(self) -> dict:
        """Return metadata from the pdf doc."""
        md = self._doc.metadata
        if not md:
            md = {}
        return md

    def _get_preserved_metadata(self) -> dict:
        """Get preserved metadata."""
        old_metadata = {}
        if self._doc.metadata:
            for key in self._METADATA_COPY_KEYS:
                if value := self._doc.metadata.get(key):
                    old_metadata[key] = value
        return old_metadata

    def save_metadata(self, metadata: Mapping) -> None:
        """Set metadata to the pdf doc."""
        preserved_metadata = self._get_preserved_metadata()
        new_metadata = {
            **preserved_metadata,
            **metadata,
        }
        self._doc.set_metadata(new_metadata)  # type: ignore

        tmp_path = self._path.with_suffix(self._TMP_SUFFIX)
        self._doc.save(
            tmp_path,
            garbage=4,
            deflate=True,
            deflate_images=False,
            deflate_fonts=True,
            encryption=fitz.PDF_ENCRYPT_KEEP,  # type: ignore
            linear=True,
            pretty=True,
            no_new_id=True,
        )
        tmp_path.replace(self._path)
