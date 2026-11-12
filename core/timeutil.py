from __future__ import annotations

from datetime import date, datetime, time, timedelta

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def parse_now(value: str | None, tz) -> datetime:
    if not value:
        return datetime.now(tz)
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=tz)


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def at(d: date, hhmm: str, tz) -> datetime:
    h, m = (int(x) for x in str(hhmm).split(":"))
    return datetime.combine(d, time(h, m), tzinfo=tz)


def next_birthday(bday, today: date) -> date:
    b = bday if isinstance(bday, date) else date.fromisoformat(str(bday))
    for y in (today.year, today.year + 1):
        try:
            c = b.replace(year=y)
        except ValueError:  # Feb 29
            c = date(y, 3, 1)
        if c >= today:
            return c
    raise AssertionError("unreachable")


def next_month_day(md: str, today: date) -> date | None:
    try:
        m, d = (int(x) for x in md.split("-"))
        return next_birthday(date(2000, m, d), today)
    except ValueError:
        return None
