"""Read-only iCalendar (.ics) adapter for Google Calendar and anything else.

For Google: Calendar settings -> "Integrate calendar" -> "Secret address in iCal
format". Put that URL (or a downloaded .ics path) in config `calendars`. For her
calendar, she shares it with you and you use its secret address, or you export
it. Supports DTSTART/DTEND (UTC, TZID, floating, all-day), DURATION-less events,
TRANSP, ATTENDEE CN, and RRULE FREQ=DAILY|WEEKLY with INTERVAL/COUNT/UNTIL/BYDAY
plus EXDATE.
"""
from __future__ import annotations

import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .base import CalendarSource, Event

_DAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _unfold(text: str) -> list[str]:
    out: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _prop(line: str):
    head, _, value = line.partition(":")
    parts = head.split(";")
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.upper()] = v.strip('"')
    return parts[0].upper(), params, value


def _dt(value: str, params: dict, tz) -> tuple[datetime, bool]:
    value = value.strip()
    if params.get("VALUE") == "DATE" or len(value) == 8:
        d = datetime.strptime(value[:8], "%Y%m%d").date()
        return datetime.combine(d, time(0, 0), tzinfo=tz), True
    if value.endswith("Z"):
        return datetime.strptime(value[:-1], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).astimezone(tz), False
    naive = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    zone = tz
    if "TZID" in params:
        try:
            zone = ZoneInfo(params["TZID"])
        except Exception:
            zone = tz
    return naive.replace(tzinfo=zone).astimezone(tz), False


def _expand(start: datetime, rule: str, exdates: set, win_end: datetime, tz):
    r = dict(p.split("=", 1) for p in rule.split(";") if "=" in p)
    freq = r.get("FREQ", "")
    interval = int(r.get("INTERVAL", 1))
    count = int(r["COUNT"]) if "COUNT" in r else None
    until = _dt(r["UNTIL"], {}, tz)[0] if "UNTIL" in r else None
    if freq not in ("DAILY", "WEEKLY"):
        yield start  # unsupported frequencies: first occurrence only
        return
    byday = sorted(_DAYS[d[-2:]] for d in r.get("BYDAY", "").split(",") if d[-2:] in _DAYS) or [start.weekday()]
    produced = 0
    for i in range(5000):
        if freq == "DAILY":
            cands = [start + timedelta(days=i * interval)]
        else:
            week0 = start - timedelta(days=start.weekday())
            cands = [week0 + timedelta(days=i * 7 * interval + wd) for wd in byday]
        for occ in cands:
            if occ < start:
                continue
            if (until and occ > until) or (count is not None and produced >= count) or occ > win_end:
                return
            produced += 1
            if occ.replace(tzinfo=None) not in exdates:
                yield occ


def parse_ics(text: str, *, tz, whose: str, calendar: str, work: bool,
              win_start: datetime, win_end: datetime) -> list[Event]:
    events: list[Event] = []
    cur: dict | None = None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {"attendees": [], "exdates": set()}
            continue
        if line == "END:VEVENT" and cur is not None:
            if "start" in cur:
                start, all_day = cur["start"]
                end = cur.get("end", (start + (timedelta(days=1) if all_day else timedelta(hours=1)), all_day))[0]
                dur = end - start
                occs = _expand(start, cur["rrule"], cur["exdates"], win_end, tz) if cur.get("rrule") else [start]
                for occ in occs:
                    oend = occ + dur
                    if oend <= win_start or occ >= win_end:
                        continue
                    events.append(Event(
                        uid=f"{cur.get('uid', '')}@{occ.isoformat()}", summary=cur.get("summary", ""),
                        start=occ, end=oend, all_day=all_day, whose=whose, calendar=calendar,
                        attendees=tuple(cur["attendees"]), description=cur.get("description", ""),
                        location=cur.get("location", ""), work=work,
                        transparent=cur.get("transp", "") == "TRANSPARENT"))
            cur = None
            continue
        if cur is None:
            continue
        name, params, value = _prop(line)
        if name == "DTSTART":
            cur["start"] = _dt(value, params, tz)
        elif name == "DTEND":
            cur["end"] = _dt(value, params, tz)
        elif name == "SUMMARY":
            cur["summary"] = value.replace("\\,", ",").replace("\\;", ";")
        elif name == "DESCRIPTION":
            cur["description"] = value.replace("\\n", "\n").replace("\\,", ",")
        elif name == "LOCATION":
            cur["location"] = value.replace("\\,", ",")
        elif name == "UID":
            cur["uid"] = value
        elif name == "TRANSP":
            cur["transp"] = value.upper()
        elif name == "RRULE":
            cur["rrule"] = value
        elif name == "EXDATE":
            for v in value.split(","):
                cur["exdates"].add(_dt(v, params, tz)[0].replace(tzinfo=None))
        elif name == "ATTENDEE":
            cur["attendees"].append(params.get("CN") or value.replace("mailto:", ""))
    return events


class ICSCalendarSource(CalendarSource):
    def __init__(self, cfg):
        self.cfg = cfg
        self._text: dict[str, str] = {}

    def _read(self, ref: str) -> str:
        if ref not in self._text:
            if ref.startswith(("http://", "https://", "webcal://")):
                url = ref.replace("webcal://", "https://", 1)
                with urllib.request.urlopen(url, timeout=20) as resp:  # read-only GET
                    self._text[ref] = resp.read().decode("utf-8", errors="replace")
            else:
                p = self.cfg.resolve(ref)
                self._text[ref] = p.read_text(encoding="utf-8") if p.exists() else ""
        return self._text[ref]

    def events(self, start, end, whose=None) -> list[Event]:
        out: list[Event] = []
        for owner in ("mine", "hers"):
            if whose and whose != owner:
                continue
            for src in self.cfg.get(f"calendars.{owner}", []) or []:
                ref = src.get("ics")
                if not ref:
                    continue
                out.extend(parse_ics(self._read(ref), tz=self.cfg.tz, whose=owner,
                                     calendar=src.get("name", owner), work=bool(src.get("work", False)),
                                     win_start=start, win_end=end))
        return sorted(out, key=lambda e: e.start)


def day_bounds(d: date, tz) -> tuple[datetime, datetime]:
    s = datetime.combine(d, time(0, 0), tzinfo=tz)
    return s, s + timedelta(days=1)
