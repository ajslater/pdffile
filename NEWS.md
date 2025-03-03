# 📰 PDFFile News

## v0.2.1

- from_datetime method becomes to_pdf_date and coerces dates from string with
  dateutil to pdf date strings.
- from_bool method becomes to_xml_bool and coerces strings and other values to
  xml bool string.

## v0.2.0

- Automatically converts pdf datestrings to python datetimes and back.
- Automatically converts pdf/xml bool string to python bools and back
- PDFFile static methods to_datetime, from_datetime and to_bool and from_bool do
  this manually.
- Deflate images on save.

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
