"""Computed view of a trip: per-day plan with cost estimates, closures, events, ordering by
distance, budget vs actual spend and booking deadlines. Used by exports, README blocks, the
calendar, the offline page and query.py, so all of them agree."""
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import yaml

from common import (REPO, SCHEMA, SLOT_ORDER, WEEKDAYS, allowed_places, closures_on, coords, d, describe_rule,
                    edition_on, editions_overlapping, estimate_yen, events_on, haversine_km, holidays, plan_items,
                    trip_nights)


def load_profile(root=REPO):
    fp = os.path.join(root, "profile.yaml")
    if not os.path.exists(fp):
        return {}
    with open(fp, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def daily_budget_yen(profile):
    b = (profile or {}).get("budget") or {}
    if b.get("daily_eur_per_person") and b.get("eur_jpy"):
        return round(b["daily_eur_per_person"] * b["eur_jpy"])
    return None


def maps_url(n, nodes, paths):
    c = coords(n)
    if c and n.get("coords_precision", "exact") == "exact":
        return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{c[0]:.6f},{c[1]:.6f}")
    city = nodes.get(paths.get(n.get("place")), {}).get("name", "")
    q = " ".join(x for x in (n.get("name"), n.get("area_detail") or "", city, "Japan") if x)
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(q)


def summary(n, keys=("id", "type", "name", "name_ja", "area", "hours", "booking", "entry", "price_range",
                     "tabelog_rating", "cuisine", "station", "address_ja", "coords", "coords_precision")):
    return {k: n[k] for k in keys if n.get(k) not in (None, "", [])}


def order_by_distance(items, start=None):
    """Keep slot order; inside a slot, visit items greedily by distance from the previous point."""
    out, prev = [], start
    by_slot = {}
    for it in items:
        by_slot.setdefault(SLOT_ORDER.get(it.get("slot"), SLOT_ORDER["day"]), []).append(it)
    for _, group in sorted(by_slot.items()):
        rest = list(group)
        while rest:
            if prev is None:
                nxt = rest[0]
            else:
                nxt = min(rest, key=lambda it: haversine_km(prev, it["_c"]) if it.get("_c") else 10 ** 6)
            rest.remove(nxt)
            out.append(nxt)
            if nxt.get("_c"):
                prev = nxt["_c"]
    return out


def day_view(nodes, paths, trip, day, profile=None, hol=None):
    hol = hol if hol is not None else holidays(nodes, trip.get("country"))
    date_ = d(day["date"])
    stay = nodes.get(day.get("stay")) if day.get("stay") else None
    start = coords(stay) if stay else None
    items = []
    for it in plan_items(day):
        n = nodes.get(it["id"])
        if not n:
            continue
        est = it.get("yen") if it.get("yen") is not None else estimate_yen(n, it.get("slot"))
        closed = closures_on(n, date_, hol) if n.get("type") in ("activity", "restaurant") else []
        row = {"slot": it.get("slot"), "id": n["id"], "type": n["type"], "name": n.get("name"),
               "est_yen": est, "maps": maps_url(n, nodes, paths)}
        for k in ("name_ja", "address_ja", "hours", "booking", "area", "tabelog_rating", "cuisine", "station"):
            if n.get(k) not in (None, "", []):
                row[k] = n[k]
        if it.get("note"):
            row["note"] = it["note"]
        if closed:
            row["closed"] = [{"rule": describe_rule(r), "partial": r.get("partial")} if r.get("partial")
                             else {"rule": describe_rule(r)} for r in closed]
        if n["type"] == "event":
            ed = edition_on(n, date_)
            if ed:
                row["edition"] = {"start": str(ed["start"]), "end": str(ed["end"])}
        c = coords(n)
        if c:
            row["coords"] = list(c)
        row["_c"] = c
        items.append(row)
    ordered = order_by_distance(items, start)
    km, prev = 0.0, start
    for it in ordered:
        if it.get("_c"):
            if prev:
                it["km_from_prev"] = round(haversine_km(prev, it["_c"]), 1)
                km += it["km_from_prev"]
            prev = it["_c"]
    for it in ordered:
        it.pop("_c", None)
    places = allowed_places(trip, day)
    events = []
    for eid in events_on(nodes, places, date_):
        e, ed = nodes[eid], edition_on(nodes[eid], date_)
        events.append({"id": eid, "name": e.get("name"), "start": str(ed["start"]), "end": str(ed["end"]),
                       "in_plan": any(i["id"] == eid for i in ordered)})
    est_known = [i["est_yen"] for i in ordered if i.get("est_yen") is not None]
    spent = sum(int(x.get("yen") or 0) for x in day.get("expenses") or [] if isinstance(x, dict))
    view = {"id": day["id"], "date": str(date_), "weekday": WEEKDAYS[date_.weekday()],
            "holiday": date_ in hol, "place": day.get("place"),
            "city": nodes.get(paths.get(day.get("place")), {}).get("name"),
            "title": day.get("title"), "stay": summary(stay, ("id", "name", "name_ja", "address_ja", "coords"))
            if stay else None,
            "visits": day.get("visits") or [], "items": ordered, "events": events,
            "straight_line_km": round(km, 1),
            "est_yen": sum(est_known), "unpriced": [i["id"] for i in ordered if i.get("est_yen") is None],
            "budget_yen": daily_budget_yen(profile),
            "spent_yen": spent if day.get("expenses") else None,
            "done": day.get("done") or [], "expenses": day.get("expenses") or []}
    return view


def deadlines(nodes, trip, day_views, schema=SCHEMA):
    """Ticket sale openings of events relevant to the trip + booking reminders for planned items."""
    out = []
    a, b = d(trip["start"]), d(trip["end"])
    places = {s.get("place") for s in trip.get("stops") or []}
    seen = set()
    for eid, e in sorted(nodes.items()):
        if e.get("type") != "event" or e.get("place") not in places:
            continue
        for ed in editions_overlapping(e, a, b):
            if ed.get("on_sale"):
                when = ed["on_sale"]
                key = (eid, "on_sale")
                if key in seen:
                    continue
                seen.add(key)
                out.append({"kind": "on_sale", "id": eid, "name": e.get("name"),
                            "when": when.isoformat() if hasattr(when, "isoformat") else str(when),
                            "date": str(d(when)), "note": ed.get("note"),
                            "for": f"{ed['start']}..{ed['end']}"})
    defaults = schema.get("book_ahead_days", {})
    for v in day_views:
        for it in v["items"]:
            n = nodes[it["id"]]
            booking = n.get("booking")
            if booking not in ("reserve", "required"):
                continue
            key = (it["id"], v["date"])
            if key in seen:
                continue
            seen.add(key)
            lead = n.get("book_ahead_days") or defaults.get(booking, 7)
            when = d(v["date"]) - timedelta(days=lead)
            out.append({"kind": "book", "id": it["id"], "name": n.get("name"), "date": str(when),
                        "for": v["date"], "booking": booking, "lead_days": lead})
    out.sort(key=lambda x: (x["date"], x.get("when", ""), x["id"]))
    return out


def trip_view(nodes, paths, trip, profile=None):
    hol = holidays(nodes, trip.get("country"))
    days = [nodes[x] for x in trip.get("days") or [] if x in nodes]
    views = [day_view(nodes, paths, trip, x, profile, hol) for x in days]
    nights = {}
    for s in trip_nights(trip).values():
        nights[s["place"]] = nights.get(s["place"], 0) + 1
    budget = daily_budget_yen(profile)
    totals = {"est_yen": sum(v["est_yen"] for v in views),
              "budget_yen": budget * len(views) if budget else None,
              "spent_yen": sum(v["spent_yen"] or 0 for v in views),
              "days_over_budget": [v["date"] for v in views if budget and v["est_yen"] > budget]}
    a, b = d(trip["start"]), d(trip["end"])
    places = {s.get("place") for s in trip.get("stops") or []}
    events = []
    for eid, e in sorted(nodes.items()):
        if e.get("type") == "event" and e.get("place") in places:
            for ed in editions_overlapping(e, a, b):
                on = [v["date"] for v in views if any(x["id"] == eid for x in v["events"])]
                events.append({"id": eid, "name": e.get("name"), "place": e.get("place"), "start": str(ed["start"]),
                               "end": str(ed["end"]), "our_days": on,
                               "in_plan": [v["date"] for v in views if any(i["id"] == eid for i in v["items"])]})
    events.sort(key=lambda x: (x["start"], x["id"]))
    return {"trip": trip["id"], "name": trip.get("name"), "start": str(a), "end": str(b),
            "nights": nights, "budget": {"daily_yen": budget, **((profile or {}).get("budget") or {})},
            "totals": totals, "events": events, "deadlines": deadlines(nodes, trip, views), "days": views}


def now_utc():
    return datetime.now(timezone.utc)
