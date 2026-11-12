"""5. Long-shift rescue.

Trigger: her calendar shows a work shift of min_hours (12) or more -> prepare her
favorite food order for 18:00 delivery that day and HALT at AWAITING_APPROVAL.
"""
from __future__ import annotations

from datetime import timedelta

from adapters.commerce import prepare_food_order
from core.timeutil import at

NAME = "long_shift"


def _is_shift(ev, cfg) -> bool:
    if ev.all_day or ev.transparent or ev.hours < float(cfg.get("min_hours", 12)):
        return False
    if ev.work or not cfg.get("require_keyword", False):
        return True
    title = f"{ev.summary} {ev.description}".lower()
    return any(k.lower() in title for k in cfg.get("shift_keywords", []))


def run(ctx, **_):
    r = ctx.run(NAME)
    cfg = ctx.cfg.wf(NAME)
    store = r.store("long_shift_state", {"handled": []})
    db = store.load()
    handled = set(db["handled"])
    horizon = ctx.now + timedelta(hours=float(cfg.get("lookahead_hours", 36)))

    for ev in ctx.events(ctx.now - timedelta(hours=24), horizon, whose="hers"):
        if ev.uid in handled or not _is_shift(ev, cfg):
            continue
        deliver = at(ev.start.date(), cfg.get("deliver_at", "18:00"), ctx.cfg.tz)
        if not (ev.start <= deliver <= ev.end):
            deliver = at(ev.end.date(), cfg.get("deliver_at", "18:00"), ctx.cfg.tz)
        if deliver < ctx.now:
            continue
        handled.add(ev.uid)
        order = prepare_food_order(str(cfg.get("order")), str(cfg.get("service")),
                                   str(cfg.get("address_label")), deliver)
        todo = ctx.cfg.todos(f"workflows.{NAME}.order", f"workflows.{NAME}.service", f"workflows.{NAME}.address_label")
        if todo:
            order["needs_config"] = todo
        r.propose("food_order",
                  trigger=f'her calendar: "{ev.summary}" {ev.start:%a %H:%M}–{ev.end:%H:%M} ({ev.hours:.1f} h)',
                  summary=f"{order['order']} via {order['vendor']} to '{order['address_label']}' at {deliver:%a %H:%M}",
                  payload=order, shift_hours=round(ev.hours, 1))

    db["handled"] = sorted(handled)
    store.save(db)
    return r.events
