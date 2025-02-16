# PDFFile

A ZipFile like API for PDFs using [PyMuPDF](https://pymupdf.readthedocs.io/) as
a backend.

Look in `pdffile.py` for exposed functions.

## Dependencies

The pymupdf dependency usually has wheels that install a local version of
libmupdf. But for some platforms (e.g. Windows) it may require libstdc++ and
c/c++ build tools installed to compile a libmupdf. More detail on this is
available in the
[pymupdf docs](https://pymupdf.readthedocs.io/en/latest/installation.html#installation-when-a-suitable-wheel-is-not-available).
