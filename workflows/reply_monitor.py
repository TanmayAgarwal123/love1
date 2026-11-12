"""1. Reply monitor.

Trigger: her message unanswered > threshold (default 20 min) -> nudge YOU.
Also flags one-word replies ("k") you sent after her message, and in your drafts, as URGENT.
"""
from __future__ import annotations

import hashlib
import re
from datetime import timedelta

NAME = "reply_monitor"


def _norm(t: str) -> str:
    return re.sub(r"[^\w]", "", t.lower())


def run(ctx, **_):
    r = ctx.run(NAME)
    cfg = ctx.cfg.wf(NAME)
    threshold = float(cfg.get("threshold_minutes", 20))
    max_age = timedelta(hours=float(cfg.get("max_age_hours", 24)))
    flags = {_norm(x) for x in cfg.get("one_word_flags", ["k"]) if _norm(str(x))}

    store = r.store("reply_monitor_state", {"seen": [], "nudged": [], "flagged": []})
    st = store.load()
    seen, nudged, flagged = set(st["seen"]), set(st["nudged"]), set(st["flagged"])
    msgs = [m for m in ctx.messages() if m.sender in ("me", "partner")]

    for i, m in enumerate(msgs):
        if m.sender != "partner" or (i > 0 and msgs[i - 1].sender == "partner"):
            continue  # only the first message of each of her turns starts the clock
        reply = next((x for x in msgs[i + 1:] if x.sender == "me"), None)
        if reply is not None:
            if m.id in seen:
                continue
            seen.add(m.id)
            gap = (reply.ts - m.ts).total_seconds() / 60
            late = gap > threshold
            r.log("reply_gap", trigger=f'her msg {m.ts:%a %d %b %H:%M} "{m.text[:60]}" -> your reply {reply.ts:%H:%M}',
                  action=f"recorded reply time {gap:.0f} min" + (" (over target)" if late else ""),
                  status="late" if late else "ok", minutes=round(gap, 1), late=late, at=m.ts.isoformat())
        else:
            waited = ctx.now - m.ts
            if timedelta(minutes=threshold) <= waited < max_age and m.id not in nudged:
                nudged.add(m.id)
                mins = int(waited.total_seconds() // 60)
                r.notify_me("She's waiting", f'{mins} min since "{m.text[:80]}" — reply with a real sentence.',
                            trigger=f"her msg {m.ts:%a %H:%M} unanswered for {mins} min (>= {threshold:.0f})",
                            waited_minutes=mins, at=m.ts.isoformat())

    for i, m in enumerate(msgs):
        if (m.sender == "me" and i > 0 and msgs[i - 1].sender == "partner"
                and _norm(m.text) in flags and m.id not in flagged):
            flagged.add(m.id)
            r.log("one_word_reply", trigger=f'you sent "{m.text}" at {m.ts:%a %H:%M} after "{msgs[i-1].text[:60]}"',
                  action="URGENT: follow up with a real reply (call, or a full sentence)", status="URGENT",
                  text=m.text, at=m.ts.isoformat())

    for d in ctx.drafts():
        key = "draft:" + hashlib.sha1(d.text.encode()).hexdigest()[:10] + d.source
        if _norm(d.text) in flags and key not in flagged:
            flagged.add(key)
            r.log("one_word_draft", trigger=f'draft {d.source}: "{d.text}"',
                  action="URGENT: don't send this — rewrite it as a real reply", status="URGENT", text=d.text)

    store.save({"seen": sorted(seen), "nudged": sorted(nudged), "flagged": sorted(flagged)})
    return r.events


def check_text(cfg, text: str) -> bool:
    flags = {_norm(x) for x in cfg.wf(NAME).get("one_word_flags", ["k"]) if _norm(str(x))}
    return _norm(text) in flags
