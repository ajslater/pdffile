"""Convert PDF Date strings to datetime and timetuple."""

import re
from datetime import datetime, timedelta, timezone
from logging import Logger, getLogger

from dateutil import parser

LOG: Logger = getLogger(__name__)
PDF_DATE_PREFIX = "D:"
DEFAULT_DTTM_TUPLE: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0)
TZ_DELIMITERS = ("+", "-")
# PDF date format: D:YYYYMMDDHHmmSSOHH'mm'
PDF_DATE_NAIVE_TEMPLATE = "D:%Y%m%d%H%M%S"
# All fields after YYYY are optional
PDF_DATE_REGEX = (
    r"^D:"
    r"(?P<year>\d{4})"
    r"(?P<month>\d{2})?"
    r"(?P<day>\d{2})?"
    r"(?P<hour>\d{2})?"
    r"(?P<minute>\d{2})?"
    r"(?P<second>\d{2})?"
    r"(?P<tz>[Z+-])?"
    r"(?P<tz_hour>\d{2})?"
    r"'(?P<tz_minute>\d{2})'?"
    r"$"
)
PDF_DATE_RE = re.compile(PDF_DATE_REGEX)

DEFAULT_DATE_COMPONENTS = {
    "month": "01",
    "day": "01",
    "hour": "00",
    "minute": "00",
    "second": "00",
}


def pdf_date_to_datetime(pdf_date: str) -> datetime:
    """
    Convert a PDF date string to a datetime object.

    Timezone-aware if the PDF date includes timezone info, naive otherwise.
    """
    m = PDF_DATE_RE.match(pdf_date.strip())
    if not m:
        reason = f"Invalid PDF date string: {pdf_date!r}"
        raise ValueError(reason)

    parts = {
        **DEFAULT_DATE_COMPONENTS,
        **{k: v for k, v in m.groupdict().items() if v is not None},
    }

    # Although I have all the timetuple parts here. Directly creating a timetuple
    # myself has some timezone issues that are just easier if datetime handles it.

    dt = datetime(  # noqa: DTZ001
        year=int(parts["year"]),
        month=int(parts["month"]),
        day=int(parts["day"]),
        hour=int(parts["hour"]),
        minute=int(parts["minute"]),
        second=int(parts["second"]),
    )

    sign = parts.get("tz")
    if sign == "Z":
        dt = dt.replace(tzinfo=timezone.utc)
    elif sign in ("+", "-"):
        offset = timedelta(
            hours=int(parts.get("tz_hour", 0)),
            minutes=int(parts.get("tz_minute", 0)),
        )
        dt = dt.replace(tzinfo=timezone(-offset if sign == "-" else offset))

    return dt


def to_datetime(pdf_date: str) -> datetime | None:
    """Convert a PDF date string to a datetime."""
    if isinstance(pdf_date, datetime):
        return pdf_date
    if not pdf_date or not pdf_date.startswith(PDF_DATE_PREFIX):
        return None
    try:
        dttm = pdf_date_to_datetime(pdf_date)
        if not dttm.tzinfo:
            dttm.replace(tzinfo=timezone.utc)
    except Exception as exc:
        dttm = None
        reason = f"Unable to parse PDF datetime {pdf_date}, using start of epoch: {exc}"
        LOG.warning(reason)
    return dttm


def datetime_to_pdf_date(dt: datetime) -> str:
    """Convert a datetime object to a PDF date string."""
    pdf_date = dt.strftime(PDF_DATE_NAIVE_TEMPLATE)

    if (offset := dt.utcoffset()) is not None:
        total_seconds = int(offset.total_seconds())
        sign = "+" if total_seconds >= 0 else "-"
        total_seconds = abs(total_seconds)
        hh = total_seconds // 3600
        mm = (total_seconds % 3600) // 60
        tz_suffix = f"{sign}{hh:02d}'{mm:02d}'"
        pdf_date += tz_suffix

    return pdf_date


def to_pdf_date(value: datetime | str) -> str | None:
    """Convert a datetime to a PDF date string."""
    if not value:
        return None

    if isinstance(value, str):
        if value.startswith(PDF_DATE_PREFIX):
            return value
        dttm = parser.parse(value)
    else:
        dttm = value

    return datetime_to_pdf_date(dttm)


def to_zipinfo_timetuple(
    value: str | datetime,
) -> tuple[int, int, int, int, int, int]:
    """Convert a pdf_date to a ZipInfo time tuple."""
    try:
        dttm = value if isinstance(value, datetime) else to_datetime(value)
        dttm_tuple = dttm.timetuple()[:6]  # pyright: ignore[reportOptionalMemberAccess], #ty: ignore[unresolved-attribute]
    except Exception as exc:
        dttm_tuple = DEFAULT_DTTM_TUPLE
        reason = f"Unable to convert pdf datetime {value} to ZipInfo timetuple, using default. {exc}."
        LOG.warning(reason)

    return dttm_tuple
