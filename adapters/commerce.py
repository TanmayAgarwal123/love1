"""Builds carts, orders and bookings as PAYLOADS + LINKS for your review.

Nothing here pays, books or submits anything. Every function returns a dict
whose `state` is AWAITING_APPROVAL; the approval queue stores it; you open the
link and finish it yourself if you approve.
"""
from __future__ import annotations

from datetime import date, datetime
from urllib.parse import quote_plus

from core.approvals import AWAITING

_FOOD_SEARCH = {
    "doordash": "https://www.doordash.com/search/store/{q}/",
    "ubereats": "https://www.ubereats.com/search?q={q}",
    "grubhub": "https://www.grubhub.com/search?queryText={q}",
    "swiggy": "https://www.swiggy.com/search?query={q}",
    "zomato": "https://www.zomato.com/search?q={q}",
}
_FLORIST_SEARCH = {
    "1-800-flowers": "https://www.1800flowers.com/search?keyword={q}",
    "ftd": "https://www.ftd.com/search?q={q}",
    "urbanstems": "https://urbanstems.com/search?q={q}",
    "fnp": "https://www.fnp.com/search?q={q}",
}
_BOOKING = {
    "opentable": "https://www.opentable.com/s?term={q}&dateTime={dt}&covers={n}",
    "resy": "https://resy.com/cities?query={q}&date={d}&seats={n}",
    "google": "https://www.google.com/search?q={q}+reservation",
}


def build_amazon_cart(items: list[dict], domain: str = "amazon.com") -> dict:
    lines, asins = [], []
    for it in items:
        asin = it.get("asin")
        url = (f"https://www.{domain}/dp/{asin}" if asin
               else f"https://www.{domain}/s?k={quote_plus(it['item'])}")
        lines.append({"item": it["item"], "asin": asin, "url": url, "qty": 1})
        if asin:
            asins.append(asin)
    cart_url = None
    if asins:
        q = "&".join(f"ASIN.{i}={a}&Quantity.{i}=1" for i, a in enumerate(asins, 1))
        cart_url = f"https://www.{domain}/gp/aws/cart/add.html?{q}"  # opens a pre-filled cart; you review it
    return {"vendor": "amazon", "lines": lines, "cart_url": cart_url, "state": AWAITING}


def prepare_food_order(order: str, service: str, address_label: str, deliver_at: datetime) -> dict:
    tmpl = _FOOD_SEARCH.get(str(service).lower())
    return {
        "vendor": service, "order": order, "address_label": address_label,
        "deliver_at": deliver_at.isoformat(timespec="minutes"),
        "link": tmpl.format(q=quote_plus(order.split(",")[0])) if tmpl else None,
        "state": AWAITING,
    }


def prepare_flower_order(*, florist: str, deliver_on: date, budget_cap, currency: str,
                         avoid: list[str], likes: list[str]) -> dict:
    tmpl = _FLORIST_SEARCH.get(str(florist).lower())
    brief = "mixed seasonal bouquet" + (f", no {', '.join(avoid)}" if avoid else "")
    return {
        "vendor": florist, "deliver_on": deliver_on.isoformat(), "budget_cap": budget_cap,
        "currency": currency, "brief": brief, "avoid": avoid, "card_note": "No reason. Just thinking of you.",
        "link": tmpl.format(q=quote_plus("bouquet")) if tmpl else None, "state": AWAITING,
    }


def prepare_booking(*, place: dict, when: datetime, party: int, site: str) -> dict:
    tmpl = _BOOKING.get(site, _BOOKING["google"])
    return {
        "vendor": site, "restaurant": place["name"], "when": when.isoformat(timespec="minutes"),
        "party_size": party,
        "link": tmpl.format(q=quote_plus(place["name"]), dt=when.strftime("%Y-%m-%dT%H:%M"),
                            d=when.date().isoformat(), n=party),
        "state": AWAITING,
    }
