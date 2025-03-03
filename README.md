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

## Data Types

MuPDF reads and writes all data types as strings. PDFFile automatically converts
pdf date strings to python datetimes and pdf/xml boolean strings to python bools
and back.

The helper functions to_datetime, to_pdf_date, to_bool, and to_xml_bool are
available on the PDFFile class.
