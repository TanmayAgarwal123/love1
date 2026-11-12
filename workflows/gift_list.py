"""2. Gift list.

Trigger: she says she wants something -> save item + date + context.
lead_days (14) before her birthday -> build an Amazon cart of the top items and HALT at AWAITING_APPROVAL.
"""
from __future__ import annotations

from datetime import timedelta

from adapters.commerce import build_amazon_cart
from core import extract
from core.timeutil import next_birthday

NAME = "gift_list"


def _key(item: str) -> str:
    return " ".join(item.lower().split())


def _score(item: dict, today) -> float:
    from datetime import date
    last = date.fromisoformat(item["last_mentioned"][:10])
    return item["mentions"] * 10 - (today - last).days * 0.1


def run(ctx, **_):
    r = ctx.run(NAME)
    cfg = ctx.cfg.wf(NAME)
    store = r.store("gifts", {"items": [], "processed": [], "carts": {}})
    db = store.load()
    processed = set(db["processed"])
    by_key = {_key(i["item"]): i for i in db["items"]}

    for m in ctx.messages():
        if m.sender != "partner" or m.id in processed:
            continue
        processed.add(m.id)
        for item in extract.wants(m.text, cfg.get("ignore", [])):
            ctxline = {"date": m.ts.date().isoformat(), "said": m.text[:200]}
            ex = by_key.get(_key(item))
            if ex:
                ex["mentions"] += 1
                ex["last_mentioned"] = m.ts.isoformat()
                ex["contexts"] = (ex["contexts"] + [ctxline])[-5:]
                r.log("gift_mentioned_again", trigger=f'she said: "{m.text[:80]}" ({m.ts:%b %d})',
                      action=f"bumped '{ex['item']}' to {ex['mentions']} mentions", status="updated",
                      item=ex["item"], at=m.ts.isoformat())
            else:
                new = {"item": item, "first_mentioned": m.ts.isoformat(), "last_mentioned": m.ts.isoformat(),
                       "mentions": 1, "contexts": [ctxline], "status": "saved"}
                db["items"].append(new)
                by_key[_key(item)] = new
                r.log("gift_saved", trigger=f'she said: "{m.text[:80]}" ({m.ts:%b %d})',
                      action=f"saved '{item}' to gift list", status="saved", item=item, at=m.ts.isoformat())

    bday_raw = ctx.cfg.get("partner.birthday")
    if bday_raw:
        today = ctx.today
        bday = next_birthday(bday_raw, today)
        lead = int(cfg.get("lead_days", 14))
        year_key = str(bday.year)
        if bday - timedelta(days=lead) <= today < bday and year_key not in db["carts"]:
            ranked = sorted((i for i in db["items"] if i["status"] == "saved"),
                            key=lambda i: _score(i, today), reverse=True)[: int(cfg.get("top_n", 3))]
            if not ranked:
                if db.get("empty_cart_logged") != today.isoformat():
                    db["empty_cart_logged"] = today.isoformat()
                    r.log("birthday_cart_empty", trigger=f"birthday {bday:%b %d} is {(bday - today).days} days out",
                          action="no saved gift ideas yet — nothing to put in a cart", status="skipped")
            else:
                cart = build_amazon_cart(ranked, cfg.get("amazon_domain", "amazon.com"))
                sizes = ctx.cfg.get("partner.sizes", {}) or {}
                ap = r.propose("amazon_cart",
                               trigger=f"birthday {bday:%b %d} is {(bday - today).days} days out (lead {lead})",
                               summary=f"{len(ranked)} gift(s): " + ", ".join(i["item"] for i in ranked),
                               payload={**cart, "sizes_for_reference": sizes,
                                        "why": [{"item": i["item"], "she_said": i["contexts"][-1]} for i in ranked]},
                               items=len(ranked))
                db["carts"][year_key] = ap["id"]
                for i in ranked:
                    i["status"] = "in_cart"
                    i["cart_id"] = ap["id"]

    db["processed"] = sorted(processed)
    store.save(db)
    return r.events
