# 📰 PDFFile News

## v0.6.3 - Apply page rotation when serving rotated image-dominant pages

- Fix: `read_image_if_dominant` / `read_full_pixmap_jpeg` returned the embedded
  image _as stored_ for pages with a `/Rotate` attribute, so scans stored
  inverted (common scanner output relying on `/Rotate 180` for display) were
  served upside down. Rotated `IMAGE_TRANSCODE` verdicts now re-render the whole
  page — which applies `/Rotate` — instead of decoding the bare image xref.
- `PageVerdict` gains `page_index` and `rotation` fields.
- Fix: `close()` saved the document whenever MuPDF marked it dirty — and MuPDF
  does that when it repairs malformed content streams in memory during read
  operations (`get_text` / `get_drawings`, both used by `classify_page`), so a
  read-only page serve could silently rewrite the file on disk. `close()` now
  saves only after explicit writes (`writestr` / `remove` / `write_metadata`).
- Fix: image-dominant pages rotated by the content-stream matrix (CTM) instead
  of `/Rotate` were still served as stored — sideways or upside down.
  Classification now derives the display rotation from `/Rotate` plus the
  placement transform, page-renders any rotated placement, and conservatively
  falls back to the PDF path for mirrored/skewed placements or rotations that
  cancel.
- Fix: `choose_pixmap_dpi` paired image pixel dimensions with the wrong axes
  for CTM-rotated placements, inflating the render DPI by the page aspect
  ratio. It now measures each image axis's placed span from the transform.
- `read_full_pixmap_jpeg(index, dpi=N)` with an explicit `dpi` now always
  renders at that DPI instead of short-circuiting to the embedded image and
  silently ignoring the override.

## v0.6.2

- Security release for dependencies.

## v0.6.1 - Auto-DPI for full-page rasterization

- New `choose_pixmap_dpi(page)` picks a render DPI matching the page's
  embedded-image resolution. Walks each image, computes its native placed DPI
  from the pixel dimensions and bbox, returns the highest value clamped to
  `[DEFAULT_PIXMAP_DPI, MAX_PIXMAP_DPI]` (150–300). Pages with no images return
  the default. Tiny tracking pixels and decorative dots are filtered via
  `min_bbox_fraction`.
- `PDFFile.read_full_pixmap_jpeg(index, dpi=None)` now defaults to the
  auto-picked DPI; pass an integer to override. Existing callers see slightly
  higher rendering quality on multi-image pages and a consistent 150 DPI floor
  on pure vector pages — comic-resolution output by default instead of the
  previous 72 DPI.
- New module-level constants `DEFAULT_PIXMAP_DPI = 150` and
  `MAX_PIXMAP_DPI = 300`.

## v0.6.0 - Image-dominant page detection

- Features
    - New `PDFFile.classify_page(index)` returns a `PageVerdict` describing how
      the page should be served: `IMAGE_DIRECT` (embedded image is browser-safe
      as-stored), `IMAGE_TRANSCODE` (embedded image needs RGB-JPEG re-encoding —
      CMYK, JBIG2, JPEG 2000, rotated pages), or `PDF_FALLBACK` (page has vector
      content; serve through the PDF path). Detection runs on parsed metadata —
      no rasterization — and costs single-digit milliseconds per page.
    - New `PDFFile.read_image_if_dominant(index)` returns `(bytes, ext)` for
      image-dominant pages or `None` for fall-through, letting browser readers
      serve comic-style PDFs as plain `<img>` instead of going through pdf.js.
    - New `PDFFile.read_full_pixmap_jpeg(index)` renders any page to RGB JPEG
      for callers that need an always-image response.
    - New `PageFormat.IMAGE_IF_DOMINANT` and `PageFormat.PIXMAP_JPEG` values for
      the `read()` interface.

- Fixes
    - `read_pdf` passes `no_new_id=True` to `tobytes()` so single-page PDF
      output is deterministic across calls. Without this, pymupdf stamps a fresh
      random `/ID` array on every save and byte-equality fixtures break on every
      run.

## v0.5.1

- Extract PDF pages as originals rather than recomposing them. Fixes a bug where
  OCR text became visible.

## v0.5.0

- Refactor all datetime processing and move to a utility file.
- API unchanged.

## v0.4.1

- Fix reading PDF metadata breaking on datetimes.
- Unreadable or unconvertable PDF datetimes are substituted with the start of
  the epoch and log a warning instead of raising an exception and abandoning
  parsing.

## v0.4.0 - Extract unaltered images

- read() also extract original image files. Format now specified with an string.
  File extension passed back in an optional props dict.
- read_image() reads the first image on a page in the original format
- read_pixmap() converts the page to a ppm.
- read_pdf() converts the page into a one page pdf.
- read_embedded_file() reads a named embedded file
- PageFormat convenience enum to show options.

## v0.3.0 - Embedded File Support

- namelist() lists embedded files.
- infolist() lists embedded files.
- read() can also read named embedded files.
- writestr() writes named embedded files. Throws if page numbers are submitted.
- remove() will remove named embedded files or pages if the name evaluates to a
  non-negative integer.

## v0.2.5

- Save with object streams compression instead of linear format.

## v0.2.4

- Parse timezone naive PDF datetimes.

## v0.2.3

- Automatically converts pdf datestrings to python datetimes and back.
- Automatically converts pdf/xml bool string to python bools and back
- PDFFile static methods to_datetime, to_pdf_date, and to_bool and to_xml_bool
  do this manually.
- Deflate images on save.

## v0.2.0-0.2.2 - Yanked

## v0.1.8

- Build with circleci

## v0.1.7

- Dependency security update

## v0.1.6

- pymupdf 1.24.0

## v0.1.5

- Support Python 3.9

## v0.1.4

- Require Python 3.10

## v0.1.3

- Documentation changes

## v0.1.2

- Fix bad reference to new_fitz as it's the default now.

## v0.1.1

- Fix up packaging and tests. No functional changes.

## v0.1.0

- A ZipFile like API for muPDF
