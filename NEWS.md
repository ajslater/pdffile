# 📰 PDFFile News

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
