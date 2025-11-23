#!/usr/bin/env python3
"""Test runner."""

from pathlib import Path

from pdffile import PDFFile

PATH = Path("../comicbox/tests/files/test_cix.pdf")

with PDFFile(PATH) as pf:
    print(pf.infolist())  # noqa: T201
