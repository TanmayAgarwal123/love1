"""6. Random flowers.

Splits time into 6–8 week windows, picks one random day in each, and lead_days
before it prepares a flower order (budget cap, avoid list) that HALTS at
AWAITING_APPROVAL. Never lands within avoid_near_birthday_days of her birthday.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from adapters.commerce import prepare_flower_order
from core.timeutil import next_birthday

NAME = "random_flowers"


def new_plan(cfg_all, window_start: date) -> dict:
    cfg = cfg_all.wf(NAME)
    rng = random.Random(f"{cfg.get('seed', '')}:{window_start.isoformat()}")
    length = rng.randint(int(cfg.get("window_weeks_min", 6)) * 7, int(cfg.get("window_weeks_max", 8)) * 7)
    end = window_start + timedelta(days=length - 1)
    bday_raw = cfg_all.get("partner.birthday")
    gap = int(cfg.get("avoid_near_birthday_days", 4))
    pick = window_start
    for _ in range(25):
        pick = window_start + timedelta(days=rng.randint(0, length - 1))
        if not bday_raw:
            break
        b = next_birthday(bday_raw, pick - timedelta(days=gap))
        if abs((b - pick).days) > gap:
            break
    return {"window_start": window_start.isoformat(), "window_end": end.isoformat(),
            "date": pick.isoformat(), "proposed": None}


def run(ctx, **_):
    r = ctx.run(NAME)
    cfg = ctx.cfg.wf(NAME)
    store = r.store("flowers_state", {"plan": None, "history": []})
    db = store.load()
    today = ctx.today

    if not db["plan"]:
        db["plan"] = new_plan(ctx.cfg, today)
        p = db["plan"]
        r.log("plan", trigger=f"new window {p['window_start']}..{p['window_end']}",
              action=f"secretly picked {p['date']} for surprise flowers", status="planned", **p)

    plan = db["plan"]
    lead = int(cfg.get("lead_days", 2))
    target = date.fromisoformat(plan["date"])
    if not plan["proposed"] and today >= target - timedelta(days=lead):
        deliver = max(target, today + timedelta(days=lead)) if today > target - timedelta(days=lead) else target
        order = prepare_flower_order(florist=str(cfg.get("florist")), deliver_on=deliver,
                                     budget_cap=cfg.get("budget_cap"), currency=str(cfg.get("currency", "USD")),
                                     avoid=list(cfg.get("avoid", []) or []),
                                     likes=list(ctx.cfg.get("partner.likes", []) or []))
        todo = ctx.cfg.todos(f"workflows.{NAME}.budget_cap", f"workflows.{NAME}.florist")
        if todo:
            order["needs_config"] = todo
        ap = r.propose("flower_order",
                       trigger=f"random day {plan['date']} in window {plan['window_start']}..{plan['window_end']} (lead {lead}d)",
                       summary=f"{order['brief']} from {order['vendor']}, cap {order['budget_cap']} {order['currency']}, "
                               f"deliver {deliver:%a %b %d}",
                       payload=order)
        plan["proposed"] = ap["id"]

    while today > date.fromisoformat(plan["window_end"]):
        db["history"].append(plan)
        plan = new_plan(ctx.cfg, date.fromisoformat(plan["window_end"]) + timedelta(days=1))
        r.log("plan", trigger=f"new window {plan['window_start']}..{plan['window_end']}",
              action=f"secretly picked {plan['date']} for surprise flowers", status="planned", **plan)
    db["plan"] = plan
    store.save(db)
    return r.events
