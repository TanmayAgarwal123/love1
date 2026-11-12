"""4. Friends CRM.

Trigger: she mentions a friend -> log name, notes, last-mentioned context.
Before any calendar event (either calendar, within lookahead) that involves a
logged friend -> write you a short briefing.
"""
from __future__ import annotations

import re
from datetime import timedelta

from core import extract

NAME = "friends_crm"


def run(ctx, **_):
    r = ctx.run(NAME)
    cfg = ctx.cfg.wf(NAME)
    store = r.store("friends", {"friends": {}, "processed": [], "briefed": []})
    db = store.load()
    processed = set(db["processed"])
    w = ctx.cfg.get("messaging.whatsapp", {}) or {}
    exclude = list(cfg.get("not_friends", []) or []) + [
        str(w.get("partner_name", "")), str(w.get("my_name", "")),
        str(ctx.cfg.get("partner.label", "")), str(ctx.cfg.get("me.label", ""))]
    exclude += [p.split()[0] for p in _restaurant_names(ctx)]

    for m in ctx.messages():
        if m.sender != "partner" or m.id in processed:
            continue
        processed.add(m.id)
        for name in extract.friends(m.text, cfg.get("known_friends", []), exclude):
            f = db["friends"].get(name)
            note = {"date": m.ts.date().isoformat(), "said": m.text[:200]}
            if f:
                f["mentions"] += 1
                f["last_mentioned"] = m.ts.isoformat()
                f["notes"] = (f["notes"] + [note])[-10:]
                status, action = "updated", f"updated {name} ({f['mentions']} mentions)"
            else:
                db["friends"][name] = {"name": name, "first_mentioned": m.ts.isoformat(),
                                       "last_mentioned": m.ts.isoformat(), "mentions": 1, "notes": [note]}
                status, action = "saved", f"logged new friend {name}"
            r.log("friend_logged", trigger=f'she said: "{m.text[:80]}" ({m.ts:%b %d})', action=action,
                  status=status, friend=name, at=m.ts.isoformat())

    horizon = ctx.now + timedelta(hours=float(cfg.get("lookahead_hours", 48)))
    briefed = set(db["briefed"])
    for ev in ctx.events(ctx.now, horizon):
        if ev.uid in briefed:
            continue
        who = [n for n in db["friends"] if extract.mentions_name(n, ev.summary, ev.description, *ev.attendees)]
        if not who:
            continue
        briefed.add(ev.uid)
        md = briefing(ev, [db["friends"][n] for n in who])
        slug = re.sub(r"[^a-z0-9]+", "-", ev.summary.lower()).strip("-")[:40]
        path = r.write_file(f"briefings/{ev.start:%Y-%m-%d}-{slug}.md", md)
        r.log("briefing", trigger=f'event "{ev.summary}" {ev.start:%a %b %d %H:%M} ({ev.whose} calendar) with {", ".join(who)}',
              action=f"wrote briefing for you -> {path.relative_to(ctx.cfg.base_dir) if path.is_relative_to(ctx.cfg.base_dir) else path}",
              status="generated", friends=who, event=ev.summary)

    db["processed"] = sorted(processed)
    db["briefed"] = sorted(briefed)
    store.save(db)
    return r.events


def _restaurant_names(ctx):
    names = [p["name"] for p in ctx.cfg.wf("date_night").get("seed_restaurants", []) or []]
    return [n for n in names if n]


def briefing(ev, friends: list[dict]) -> str:
    lines = [f"# Briefing: {ev.summary}", "",
             f"**When:** {ev.start:%a %b %d, %H:%M}–{ev.end:%H:%M}" + (f"  \n**Where:** {ev.location}" if ev.location else ""),
             ""]
    for f in friends:
        last = f["notes"][-1]
        lines += [f"## {f['name']}",
                  f"- Mentioned {f['mentions']}x; last on {last['date']}.",
                  f"- What she said last: “{last['said']}”"]
        older = f["notes"][-3:-1]
        for n in older:
            lines.append(f"- Earlier ({n['date']}): “{n['said']}”")
        lines.append(f"- Ask {f['name']} about the latest above — and remember she'll notice you remembered.")
        lines.append("")
    return "\n".join(lines)
