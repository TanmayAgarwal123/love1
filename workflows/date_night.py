"""3. Date night.

Trigger: Monday -> find a free evening this week on BOTH calendars, pick the top
unvisited place from the restaurant list, prepare a booking, HALT at AWAITING_APPROVAL.
Also adds restaurants she mentions ("we should try X") to the list on every run.
"""
from __future__ import annotations

from datetime import timedelta

from adapters.commerce import prepare_booking
from core import extract
from core.timeutil import DAY_NAMES, at, week_start

NAME = "date_night"


def _store(r, ctx):
    seed = [{"name": p["name"], "cuisine": p.get("cuisine"), "note": p.get("note"), "source": "seed",
             "priority": 1, "mentions": 0, "visited": False, "added": None}
            for p in ctx.cfg.wf(NAME).get("seed_restaurants", []) or []]
    return r.store("restaurants", {"places": seed, "processed": [], "booked_weeks": []})


def run(ctx, force: bool = False, **_):
    r = ctx.run(NAME)
    cfg = ctx.cfg.wf(NAME)
    store = _store(r, ctx)
    db = store.load()
    processed = set(db["processed"])
    by_name = {p["name"].lower(): p for p in db["places"]}

    for m in ctx.messages():
        if m.id in processed or m.sender not in ("me", "partner"):
            continue
        processed.add(m.id)
        for name in extract.restaurants(m.text):
            p = by_name.get(name.lower())
            if p:
                p["mentions"] += 1
                if m.sender == "partner":
                    p["priority"] = max(p["priority"], 2)
                continue
            p = {"name": name, "cuisine": None, "note": m.text[:160], "source": f"mention:{m.sender}",
                 "priority": 2 if m.sender == "partner" else 1, "mentions": 1, "visited": False,
                 "added": m.ts.isoformat()}
            db["places"].append(p)
            by_name[name.lower()] = p
            r.log("restaurant_added", trigger=f'"{m.text[:80]}" ({m.ts:%b %d})',
                  action=f"added '{name}' to want-to-try list", status="saved", place=name, at=m.ts.isoformat())

    week = week_start(ctx.today).isoformat()
    if (ctx.now.weekday() == 0 or force) and week not in db["booked_weeks"]:
        _plan(ctx, r, cfg, db, week)

    db["processed"] = sorted(processed)
    store.save(db)
    return r.events


def _free_evenings(ctx, cfg):
    tz = ctx.cfg.tz
    ws = week_start(ctx.today)
    out, busy_evidence = [], []
    for k in range(7):
        d = ws + timedelta(days=k)
        if d < ctx.today:
            continue
        s, e = at(d, cfg.get("evening_start", "18:30"), tz), at(d, cfg.get("evening_end", "22:00"), tz)
        if s < ctx.now:
            continue
        clashes = [ev for ev in ctx.events(s, e) if not ev.transparent and ev.start < e and ev.end > s]
        if clashes:
            busy_evidence.append(f"{DAY_NAMES[d.weekday()]}: " + "; ".join(f"{c.whose}:{c.summary}" for c in clashes))
        else:
            out.append(d)
    return out, busy_evidence


def _plan(ctx, r, cfg, db, week):
    free, busy = _free_evenings(ctx, cfg)
    if not free:
        db["booked_weeks"].append(week)
        r.log("no_free_evening", trigger=("busy: " + " | ".join(busy)) if busy else "no evenings left this week",
              action="no shared free evening this week — nothing proposed", status="skipped")
        return
    pref = [p for p in cfg.get("preferred_days", DAY_NAMES)]
    free.sort(key=lambda d: pref.index(DAY_NAMES[d.weekday()]) if DAY_NAMES[d.weekday()] in pref else 99)
    day = free[0]
    places = sorted((p for p in db["places"] if not p.get("visited") and not p.get("proposed")),
                    key=lambda p: (-p["priority"], -p["mentions"], p.get("added") or ""))
    if not places:
        r.log("no_restaurant", trigger=f"free evening {day:%a %b %d}", action="restaurant list has no unvisited places",
              status="skipped")
        return
    place = places[0]
    when = at(day, cfg.get("reservation_time", "19:30"), ctx.cfg.tz)
    payload = prepare_booking(place=place, when=when, party=int(cfg.get("party_size", 2)),
                              site=cfg.get("booking_site", "opentable"))
    ap = r.propose("restaurant_booking",
                   trigger=f"Monday scan: both calendars free {day:%a %b %d} evening; busy: {' | '.join(busy) or 'none'}",
                   summary=f"{place['name']} on {when:%a %b %d %H:%M} for {payload['party_size']}",
                   payload=payload, date=day.isoformat(), place=place["name"])
    place["proposed"] = ap["id"]
    db["booked_weeks"].append(week)


def on_done(ctx, approval: dict, live: bool):
    """You marked a date night as held -> mark the restaurant visited."""
    from core.context import WorkflowRun
    r = WorkflowRun(ctx, NAME)
    r.live, r.mode = live, "live" if live else "dry_run"
    store = _store(r, ctx)
    db = store.load()
    for p in db["places"]:
        if p["name"] == approval["payload"].get("restaurant"):
            p["visited"] = True
    store.save(db)
