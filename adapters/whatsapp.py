"""WhatsApp "Export chat" (.txt, without media) reader. Manual import, read-only.

Drop exports into messaging.whatsapp.export_dir. Re-exports may overlap; messages
are de-duplicated. Supports Android ("12/11/26, 9:41 pm - Name: text") and iOS
("[12/11/26, 9:41:03 PM] Name: text") formats, 12h or 24h clocks.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

from .base import Message, MessageSource

_TIME = r"\d{1,2}[:.]\d{2}(?:[:.]\d{2})?(?:\s?[AaPp]\.?\s?[Mm]\.?)?"
_DATE = r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"
_IOS = re.compile(rf"^\[(?P<d>{_DATE}),?\s+(?P<t>{_TIME})\]\s(?P<who>[^:]+?):\s(?P<text>.*)$")
_ANDROID = re.compile(rf"^(?P<d>{_DATE}),?\s+(?P<t>{_TIME})\s[-–]\s(?P<who>[^:]+?):\s(?P<text>.*)$")
_SYSTEM = re.compile(rf"^\[?{_DATE},?\s+{_TIME}\]?\s")
_INVIS = str.maketrans({" ": " ", "\xa0": " ", "‎": None, "‏": None, "﻿": None})


def _parse_ts(d: str, t: str, order: str, tz) -> datetime:
    a, b, y = (int(x) for x in re.split(r"[/.-]", d))
    day, month = (a, b) if order == "dmy" else (b, a)
    if y < 100:
        y += 2000
    t = t.replace(".", ":").strip()
    ampm = None
    m = re.search(r"([AaPp])\.?\s?[Mm]\.?$", t)
    if m:
        ampm = m.group(1).lower()
        t = t[: m.start()].strip()
    parts = [int(x) for x in t.split(":")]
    hh, mm = parts[0], parts[1]
    ss = parts[2] if len(parts) > 2 else 0
    if ampm == "p" and hh != 12:
        hh += 12
    if ampm == "a" and hh == 12:
        hh = 0
    return datetime(y, month, day, hh, mm, ss, tzinfo=tz)


def parse_export(text: str, *, my_name: str, partner_name: str, date_order: str, tz,
                 source: str = "") -> list[Message]:
    rows: list[list] = []
    for raw in text.translate(_INVIS).splitlines():
        line = raw.rstrip()
        m = _IOS.match(line) or _ANDROID.match(line)
        if m:
            who = m.group("who").strip()
            if who.casefold() == my_name.casefold():
                sender = "me"
            elif who.casefold() == partner_name.casefold():
                sender = "partner"
            else:
                sender = who
            rows.append([_parse_ts(m.group("d"), m.group("t"), date_order, tz), sender, m.group("text")])
        elif _SYSTEM.match(line):
            continue  # "Messages are end-to-end encrypted", "X changed the group name", ...
        elif rows:
            rows[-1][2] += "\n" + line
    out, seen = [], {}
    for ts, sender, body in rows:
        key = f"{ts.isoformat()}|{sender}|{body}"
        n = seen.get(key, 0)
        seen[key] = n + 1
        mid = hashlib.sha1(f"{key}|{n}".encode()).hexdigest()[:12]
        out.append(Message(id=mid, ts=ts, sender=sender, text=body.strip(), source=source))
    return out


class WhatsAppExportSource(MessageSource):
    def __init__(self, cfg):
        w = cfg.get("messaging.whatsapp", {}) or {}
        self.cfg = cfg
        self.export_dir = cfg.resolve(w.get("export_dir", "imports/whatsapp"))
        self.drafts_dir = cfg.resolve(w.get("drafts_dir", "imports/drafts"))
        self.my_name = str(w.get("my_name", "Me"))
        self.partner_name = str(w.get("partner_name", "Partner"))
        self.date_order = w.get("date_order", "dmy")
        self._cache: list[Message] | None = None

    def messages(self) -> list[Message]:
        if self._cache is None:
            by_id: dict[str, Message] = {}
            if self.export_dir.exists():
                for f in sorted(self.export_dir.glob("*.txt")):
                    for m in parse_export(f.read_text(encoding="utf-8", errors="replace"),
                                          my_name=self.my_name, partner_name=self.partner_name,
                                          date_order=self.date_order, tz=self.cfg.tz, source=f.name):
                        by_id[m.id] = m
            self._cache = sorted(by_id.values(), key=lambda m: m.ts)
        return self._cache

    def drafts(self) -> list[Message]:
        out = []
        if self.drafts_dir.exists():
            for f in sorted(self.drafts_dir.glob("*.txt")):
                body = f.read_text(encoding="utf-8").strip()
                mid = hashlib.sha1(f"{f.name}|{body}".encode()).hexdigest()[:12]
                ts = datetime.fromtimestamp(f.stat().st_mtime, tz=self.cfg.tz)
                out.append(Message(id=mid, ts=ts, sender="me", text=body, source=f.name))
        return out
