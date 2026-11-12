"""Sunday dashboard: aggregates the week's logs into four headline metrics,
compares with last week, and calls out every drop with a specific fix."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from statistics import mean

from core.approvals import AWAITING
from core.timeutil import DAY_NAMES, next_birthday, next_month_day, week_start


def _when(rec) -> datetime:
    return datetime.fromisoformat(rec["data"].get("at") or rec["ts"])


def week_metrics(records: list[dict], start: date) -> dict:
    end = start + timedelta(days=7)
    wk = [r for r in records if start <= _when(r).date() < end]
    gaps = [r for r in wk if r["kind"] == "reply_gap"]
    late = [r for r in gaps if r["data"].get("late")]
    approved = lambda wf: [r for r in wk if r["workflow"] == wf and r["kind"] == "approved"]
    done = lambda wf: [r for r in wk if r["workflow"] == wf and r["kind"] == "done"]
    return {
        "avg_reply_min": float(round(mean(r["data"]["minutes"] for r in gaps), 1)) if gaps else None,
        "replies": len(gaps),
        "late": late,
        "date_nights_proposed": sum(1 for r in wk if r["workflow"] == "date_night" and r["kind"] == "proposal"),
        "date_nights_booked": len(approved("date_night")),
        "date_nights_held": len(done("date_night")),
        "gifts_saved": sum(1 for r in wk if r["kind"] == "gift_saved"),
        "gifts_ordered": sum(int(r["data"].get("items", 1)) for r in approved("gift_list")),
        "k_replies": [r for r in wk if r["kind"] == "one_word_reply"],
        "activity": Counter(r["workflow"] for r in wk),
        "dry_run_events": sum(1 for r in wk if r["mode"] == "dry_run"),
        "events": len(wk),
    }


def _days(recs) -> str:
    ds = sorted({_when(r).weekday() for r in recs})
    return "/".join(DAY_NAMES[d] for d in ds)


def drops(cur: dict, prev: dict) -> list[str]:
    out = []
    a, b = cur["avg_reply_min"], prev["avg_reply_min"]
    if a is not None and b is not None and a > b:
        detail = f" — {len(cur['late'])} thread(s) went past 20 min on {_days(cur['late'])}" if cur["late"] else ""
        out.append(f"⚠️ Reply time slipped to {a:.0f} min (from {b:.0f}){detail}. Fix: pin her chat and turn "
                   f"its notifications on; if you can't talk, send one real sentence (\"in a meeting till 3, "
                   f"then I'm yours\") instead of going silent.")
    if len(cur["k_replies"]) > len(prev["k_replies"]) or cur["k_replies"]:
        quotes = ", ".join(f"\"{r['data'].get('text')}\" on {DAY_NAMES[_when(r).weekday()]}" for r in cur["k_replies"])
        if len(cur["k_replies"]) > len(prev["k_replies"]):
            out.append(f"⚠️ 'k'-style replies up to {len(cur['k_replies'])} (from {len(prev['k_replies'])}, target 0): "
                       f"{quotes}. Fix: follow up on each today with a real reply — or call.")
        else:
            out.append(f"⚠️ 'k'-style replies: {len(cur['k_replies'])} (target 0): {quotes}. Fix: follow up today.")
    for key, label, fix in (
        ("date_nights_booked", "Date nights booked",
         "approve this week's proposal (python cli.py approvals list) or run `python cli.py run date_night --force`."),
        ("date_nights_held", "Date nights held",
         "after a date, mark it held: `python cli.py approvals done <id>`; if it didn't happen, rebook this week."),
        ("gifts_saved", "Gifts saved",
         "import a fresh WhatsApp export so the gift list can hear her 'I want…' mentions."),
        ("gifts_ordered", "Gifts ordered",
         "review the pending gift cart before her birthday (python cli.py approvals list)."),
    ):
        if cur[key] < prev[key]:
            out.append(f"⚠️ {label} dropped to {cur[key]} (from {prev[key]}). Fix: {fix}")
    return out


def _fmt(v, unit=""):
    return "—" if v is None else f"{v}{unit}"


def _arrow(cur, prev, lower_is_better=False):
    if cur is None or prev is None or cur == prev:
        return "→"
    better = cur < prev if lower_is_better else cur > prev
    return "▲ better" if better else "▼ worse"


def render(cfg, records: list[dict], week_ending: date, pending: list[dict] | None = None) -> str:
    start = week_start(week_ending)
    cur, prev = week_metrics(records, start), week_metrics(records, start - timedelta(days=7))
    rows = [
        ("Average reply time", _fmt(cur["avg_reply_min"], " min"), _fmt(prev["avg_reply_min"], " min"),
         _arrow(cur["avg_reply_min"], prev["avg_reply_min"], True)),
        ("Date nights booked / held", f"{cur['date_nights_booked']} / {cur['date_nights_held']}",
         f"{prev['date_nights_booked']} / {prev['date_nights_held']}",
         _arrow(cur["date_nights_booked"] + cur["date_nights_held"], prev["date_nights_booked"] + prev["date_nights_held"])),
        ("Gifts saved / ordered", f"{cur['gifts_saved']} / {cur['gifts_ordered']}",
         f"{prev['gifts_saved']} / {prev['gifts_ordered']}",
         _arrow(cur["gifts_saved"] + cur["gifts_ordered"], prev["gifts_saved"] + prev["gifts_ordered"])),
        ("'k'-style replies sent (target 0)", str(len(cur["k_replies"])), str(len(prev["k_replies"])),
         _arrow(len(cur["k_replies"]), len(prev["k_replies"]), True)),
    ]
    L = [f"# Sunday dashboard — week of {start:%b %d} – {week_ending:%b %d, %Y}", ""]
    if cur["dry_run_events"]:
        L += [f"_Includes {cur['dry_run_events']} dry-run event(s): proposals were logged, nothing was sent or bought._", ""]
    L += ["| Metric | This week | Last week | Trend |", "|---|---|---|---|"]
    L += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows]
    if cur["date_nights_proposed"]:
        L.append(f"\n_{cur['date_nights_proposed']} date night(s) proposed this week, waiting on your approval._")
    L += ["", "## What dropped (and the fix)"]
    d = drops(cur, prev)
    L += d if d else ["✅ Nothing dropped vs last week."]
    L += ["", "## Per-workflow activity", "| Workflow | Events this week | Last week |", "|---|---|---|"]
    for wf in ("reply_monitor", "gift_list", "date_night", "friends_crm", "long_shift", "random_flowers", "referee"):
        L.append(f"| {wf} | {cur['activity'].get(wf, 0)} | {prev['activity'].get(wf, 0)} |")
    if pending:
        L += ["", "## Waiting on your approval"]
        L += [f"- `{p['id']}` {p['workflow']}: {p['summary']}" for p in pending]
    L += ["", "## Coming up (next 14 days)"]
    upcoming = []
    nxt = week_ending + timedelta(days=1)
    if cfg.get("partner.birthday"):
        b = next_birthday(cfg.get("partner.birthday"), nxt)
        if (b - nxt).days <= 14:
            upcoming.append((b, f"{cfg.get('partner.label', 'Her')}'s birthday"))
    for ms in cfg.get("partner.milestones", []) or []:
        md = next_month_day(str(ms.get("date", "")), nxt)
        if md and (md - nxt).days <= 14:
            upcoming.append((md, ms.get("label", "milestone")))
    L += [f"- {d:%a %b %d}: {label}" for d, label in sorted(upcoming)] or ["- Nothing on the calendar of milestones."]
    return "\n".join(L) + "\n"


def run(ctx, week_ending: date | None = None, **_):
    if week_ending is None:
        t = ctx.today
        week_ending = t + timedelta(days=(6 - t.weekday()))  # this week's Sunday
    records = ctx.log.read()
    pending = ctx.approvals(dry=False).list(AWAITING) + ctx.approvals(dry=True).list(AWAITING)
    md = render(ctx.cfg, records, week_ending, pending)
    out = ctx.cfg.path("reports") / f"{week_ending.isoformat()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    return out, md
