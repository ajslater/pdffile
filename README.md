# PDFFile

A ZipFile like API for PDFs using [PyMuPDF](https://pymupdf.readthedocs.io/) as
a backend.

## 📜 News

PDFFile has a [NEWS file](NEWS.md) to summarize changes that affect users.

## 🕸️ HTML Docs

[HTML formatted docs are available here](https://pdffile.readthedocs.io)

## 📦 Dependencies

PDFFile depends on [PyMuPDF](https://pymupdf.readthedocs.io/) 2.0 or later.

PyMuPDF 2.0 bundles its layout-analysis stack: the `pymupdf` wheel pulls in
`onnxruntime`, `numpy`, `networkx`, `psutil`, `pyyaml`, `tabulate`,
`pymupdf-layout` and `pymupdf4llm`, and `import pymupdf` activates the ONNX
layout model. PDFFile uses none of it; it only renders pages, extracts images
and embedded files, and reads and writes metadata. PyMuPDF is
[deferring that import](https://github.com/pymupdf/PyMuPDF/issues/5196) in a
future release.

### PyMuPDF Lite

[`pymupdf-lite`](https://pypi.org/project/pymupdf-lite/) is PyMuPDF without the
layout engine: no dependencies, about a quarter of the install size, the same
`import pymupdf` API, and PDFFile's test suite passes on it. PDFFile declares
`pymupdf`, so swapping takes a step. With pip, install `pymupdf-lite` and
PDFFile's other dependencies first, then PDFFile without its dependencies:

```sh
pip install pymupdf-lite filetype python-dateutil
pip install --no-deps comicbox-pdffile
```

With uv, drop PDFFile's `pymupdf` requirement from the dependency graph and
depend on `pymupdf-lite` directly:

```toml
[tool.uv]
exclude-dependencies = ["pymupdf"]
```

Two caveats as of PyMuPDF 2.0:

- `pymupdf-lite` has no Linux arm64 (aarch64) wheel, so pip builds MuPDF from
  source there. The full `pymupdf` package does have one.
- `pymupdf` and `pymupdf-lite` install the same files. Never install both in one
  environment; uninstalling either breaks the other.

### Wheels

PyMuPDF 2.0 ships wheels for Linux x86_64 and aarch64, macOS arm64 and Windows
x64. `pymupdf-lite` adds macOS x86_64, musl Linux x86_64 and Windows x86 and
arm64. Anywhere else pip compiles MuPDF, which needs a C/C++ toolchain. See the
[PyMuPDF installation docs](https://pymupdf.readthedocs.io/en/latest/installation.html#installation-when-a-suitable-wheel-is-not-available).

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
