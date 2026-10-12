"""Conservative Open Library Edition publication-year parser v1.

Returns (year_or_none, parse_status).
Does not infer a conceptual literary work's first publication year.
"""

import re
from datetime import date

MONTHS = {
    name.lower(): i
    for i, names in enumerate([
        (),
        ("january", "jan"),
        ("february", "feb"),
        ("march", "mar"),
        ("april", "apr"),
        ("may",),
        ("june", "jun"),
        ("july", "jul"),
        ("august", "aug"),
        ("september", "sep", "sept"),
        ("october", "oct"),
        ("november", "nov"),
        ("december", "dec"),
    ])
    if i
    for name in names
}


def parse_publish_date(value):
    if value is None or value == "":
        return None, "MISSING"

    if not isinstance(value, str):
        return None, "UNPARSEABLE"

    s = value.strip()
    if not s:
        return None, "MISSING"

    # Exactly four digits.
    if re.fullmatch(r"\d{4}", s):
        year = int(s)
        if 1 <= year <= 9999:
            return year, "EXACT_YEAR"
        return None, "UNPARSEABLE"

    # ISO full date: YYYY-MM-DD.
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        year, month, day = map(int, m.groups())
        try:
            date(year, month, day)
            return year, "ISO_FULL_DATE"
        except ValueError:
            return None, "UNPARSEABLE"

    # English full date: May 18, 2011.
    m = re.fullmatch(
        r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", s
    )
    if m:
        month = MONTHS.get(m.group(1).lower())
        day = int(m.group(2))
        year = int(m.group(3))
        if month:
            try:
                date(year, month, day)
                return year, "ENGLISH_FULL_DATE"
            except ValueError:
                pass
        return None, "UNPARSEABLE"

    # English month/year: July 2003.
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})", s)
    if m:
        month = MONTHS.get(m.group(1).lower())
        year = int(m.group(2))
        if month and 1 <= year <= 9999:
            return year, "ENGLISH_MONTH_YEAR"
        return None, "UNPARSEABLE"

    # Explicit year with zeroed date components.
    m = re.fullmatch(r"(\d{4})/00/00", s)
    if m:
        year = int(m.group(1))
        if 1 <= year <= 9999:
            return year, "YEAR_WITH_INVALID_DATE_COMPONENTS"
        return None, "UNPARSEABLE"

    # Incomplete decade indication such as 189-?
    if re.fullmatch(r"\d{3}-\?", s):
        return None, "AMBIGUOUS"

    return None, "UNPARSEABLE"
