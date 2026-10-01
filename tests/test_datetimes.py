"""
PDF date strings parse to datetimes and round-trip back.

The spec format is ``D:YYYY[MM[DD[HH[mm[SS[O[HH['mm']]]]]]]]`` where every
field after the year is optional and ``O`` is ``Z``, ``+`` or ``-``. Producers
often drop one or both apostrophes around the tz minutes.
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from pdffile.datetimes import (
    DEFAULT_DTTM_TUPLE,
    datetime_to_pdf_date,
    pdf_date_to_datetime,
    to_datetime,
    to_pdf_date,
    to_zipinfo_timetuple,
)

_YMDHMS = (2020, 1, 2, 3, 4, 5)

# pdf date, expected (Y, M, D, h, m, s), expected utcoffset (None if naive)
VALID_PDF_DATES = (
    ("D:2020", (2020, 1, 1, 0, 0, 0), None),
    ("D:202003", (2020, 3, 1, 0, 0, 0), None),
    ("D:20200304", (2020, 3, 4, 0, 0, 0), None),
    ("D:2020030405", (2020, 3, 4, 5, 0, 0), None),
    ("D:202003040506", (2020, 3, 4, 5, 6, 0), None),
    ("D:20200102030405", _YMDHMS, None),
    ("D:20200102030405Z", _YMDHMS, timedelta(0)),
    ("D:20200102030405Z00'00'", _YMDHMS, timedelta(0)),
    ("D:20200102030405+05", _YMDHMS, timedelta(hours=5)),
    ("D:20200102030405+05'", _YMDHMS, timedelta(hours=5)),
    ("D:20200102030405+0530", _YMDHMS, timedelta(hours=5, minutes=30)),
    ("D:20200102030405+05'30", _YMDHMS, timedelta(hours=5, minutes=30)),
    ("D:20200102030405+05'30'", _YMDHMS, timedelta(hours=5, minutes=30)),
    ("D:20200102030405-08'00'", _YMDHMS, timedelta(hours=-8)),
    ("D:20200102030405-08'30'", _YMDHMS, -timedelta(hours=8, minutes=30)),
    (" D:20200102030405 ", _YMDHMS, None),
)

INVALID_PDF_DATES = (
    "2020",
    "D:",
    "D:20",
    "D:20201",
    "D:2020010203040506",
    "D:20200102030405+5",
    "D:20200102030405+05'3",
    "D:20200102030405X",
    "D:20201301",
)


@pytest.mark.parametrize(("pdf_date", "parts", "offset"), VALID_PDF_DATES)
def test_pdf_date_to_datetime(pdf_date, parts, offset):
    """Every optional-field variant parses with the right fields and offset."""
    dttm = pdf_date_to_datetime(pdf_date)
    assert dttm.timetuple()[:6] == parts
    assert dttm.utcoffset() == offset


@pytest.mark.parametrize("pdf_date", INVALID_PDF_DATES)
def test_pdf_date_to_datetime_invalid(pdf_date):
    """Malformed dates raise rather than parse to something wrong."""
    with pytest.raises(ValueError, match=r"."):
        pdf_date_to_datetime(pdf_date)


@pytest.mark.parametrize(("pdf_date", "parts", "offset"), VALID_PDF_DATES)
def test_round_trip(pdf_date, parts, offset):
    """Parsed dates serialize back to a pdf date that parses identically."""
    dttm = pdf_date_to_datetime(pdf_date)
    round_tripped = pdf_date_to_datetime(datetime_to_pdf_date(dttm))
    assert round_tripped == dttm
    assert round_tripped.timetuple()[:6] == parts
    assert round_tripped.utcoffset() == offset


@pytest.mark.parametrize(
    ("dttm", "pdf_date"),
    [
        (datetime(*_YMDHMS, tzinfo=UTC), "D:20200102030405+00'00'"),
        (
            datetime(*_YMDHMS, tzinfo=timezone(timedelta(hours=5, minutes=30))),
            "D:20200102030405+05'30'",
        ),
        (
            datetime(*_YMDHMS, tzinfo=timezone(-timedelta(hours=8, minutes=30))),
            "D:20200102030405-08'30'",
        ),
    ],
)
def test_datetime_to_pdf_date(dttm, pdf_date):
    """Aware datetimes serialize with a quoted HH'mm' offset."""
    assert datetime_to_pdf_date(dttm) == pdf_date


@pytest.mark.parametrize(("pdf_date", "parts", "offset"), VALID_PDF_DATES)
def test_to_datetime_is_aware(pdf_date, parts, offset):
    """to_datetime treats naive pdf dates as UTC and keeps explicit offsets."""
    dttm = to_datetime(pdf_date.strip())
    assert dttm is not None
    assert dttm.timetuple()[:6] == parts
    assert dttm.utcoffset() == (timedelta(0) if offset is None else offset)


@pytest.mark.parametrize("pdf_date", ["", "2020", "D:garbage", "D:20201301"])
def test_to_datetime_invalid(pdf_date):
    """Unparsable values return None instead of raising."""
    assert to_datetime(pdf_date) is None


def test_to_pdf_date_round_trip():
    """A naive pdf date round-trips through the public API as explicit UTC."""
    dttm = to_datetime("D:20200102030405")
    assert dttm is not None
    assert to_pdf_date(dttm) == "D:20200102030405+00'00'"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("D:20200102030405", _YMDHMS),
        ("D:20200102030405-08'30'", _YMDHMS),
        (datetime(*_YMDHMS, tzinfo=UTC), _YMDHMS),
        ("", DEFAULT_DTTM_TUPLE),
        ("D:garbage", DEFAULT_DTTM_TUPLE),
    ],
)
def test_to_zipinfo_timetuple(value, expected):
    """ZipInfo tuples use the pdf date's wall clock, or the default."""
    assert to_zipinfo_timetuple(value) == expected
