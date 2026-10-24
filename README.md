# PDFFile

A ZipFile like API for PDFs using [PyMuPDF](https://pymupdf.readthedocs.io/) as
a backend.

## 📜 News

PDFFile has a [NEWS file](NEWS.md) to summarize changes that affect users.

## 🕸️ HTML Docs

[HTML formatted docs are available here](https://pdffile.readthedocs.io)

## 📦 Dependencies

PDFFile depends on [`pymupdf-lite`](https://pypi.org/project/pymupdf-lite/),
[PyMuPDF](https://pymupdf.readthedocs.io/) without the layout-analysis engine.
It has no dependencies of its own and provides the same `import pymupdf` API.
PDFFile only renders pages, extracts images and embedded files, and reads and
writes metadata, so it needs none of the ONNX layout stack the full `pymupdf`
package pulls in.

`pymupdf-lite` ships abi3 wheels for Python 3.11 and later on Linux x86_64 and
aarch64 (glibc), musl Linux x86_64, macOS x86_64 and arm64, and Windows x86, x64
and arm64. Anywhere else pip compiles MuPDF from source, which needs a C/C++
toolchain. See the
[PyMuPDF installation docs](https://pymupdf.readthedocs.io/en/latest/installation.html#installation-when-a-suitable-wheel-is-not-available).

### Full PyMuPDF

`pymupdf` and `pymupdf-lite` install the same files. Never install both in one
environment; uninstalling either breaks the other.

If something else in your environment needs the full `pymupdf` package, install
it in place of `pymupdf-lite`. With uv, drop `pymupdf-lite` from the dependency
graph and depend on `pymupdf` directly:

```toml
[tool.uv]
exclude-dependencies = ["pymupdf-lite"]
```

With pip, install `pymupdf` and PDFFile's other dependencies first, then PDFFile
without its dependencies:

```sh
pip install pymupdf filetype python-dateutil
pip install --no-deps comicbox-pdffile
```

## 🧶 Data Types

MuPDF reads and writes all data types as strings. PDFFile automatically converts
pdf date strings to python datetimes and pdf/xml boolean strings to python bools
and back.

The helper functions to_datetime, to_pdf_date, to_bool, and to_xml_bool are
available on the PDFFile class.

## 🛠️ API

Attached to these docs in the navigation header there are some auto generated
API docs that might be better than nothing. But the code is really small and
shouldn't be difficult to interpret.

## 🛠 Development

PDFfile code is hosted at [Github](https://github.com/ajslater/pdffile)
