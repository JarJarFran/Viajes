"""Computed view of a trip: per-day plan with cost estimates, closures, events, sunrise/sunset,
plan warnings (time of day, pricey meals, shorter visiting order), budget vs actual spend and
booking deadlines. Used by exports, README blocks, the
calendar, the offline page and query.py, so all of them agree."""
import os
from datetime import datetime, timedelta, timezone  # noqa: F401
from urllib.parse import quote_plus

import yaml

from common import (REPO, SCHEMA, SLOT_ORDER, SLOT_WINDOWS, WEEKDAYS, allowed_places, closures_on, convert,
                    coords, country_of, currency_of, d, describe_rule, edition_on, editions_overlapping, estimate,
                    events_on, haversine_km, hhmm, holidays, money_range, opening_windows, parse_hours, plan_items,
                    soft_closure, strict_cap, sun_times, trip_nights, trip_places, utc_offset_hours)


def load_profile(root=REPO):
    fp = os.path.join(root, "profile.yaml")
    if not os.path.exists(fp):
        return {}
    with open(fp, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def fx_rates(profile):
    """Units of each currency per euro, from profile budget.fx (legacy eur_jpy still understood)."""
    b = (profile or {}).get("budget") or {}
    fx = dict(b.get("fx") or {})
    if b.get("eur_jpy") and "JPY" not in fx:
        fx["JPY"] = b["eur_jpy"]
    return fx


def daily_budget(profile, cur="JPY"):
    """Daily spending budget per person in `cur` (daily_eur_per_person x the euro rate)."""
    b = (profile or {}).get("budget") or {}
    rate = fx_rates(profile).get(cur)
    if b.get("daily_eur_per_person") and rate:
        return round(b["daily_eur_per_person"] * rate)
    return None


def maps_url(n, nodes, paths):
    c = coords(n)
    if c and n.get("coords_precision", "exact") == "exact":
        return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{c[0]:.6f},{c[1]:.6f}")
    city = nodes.get(paths.get(n.get("place")), {}).get("name", "")
    country = country_of(n, nodes).get("name", "")
    q = " ".join(x for x in (n.get("name"), n.get("area_detail") or "", city, country) if x)
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(q)


def summary(n, keys=("id", "type", "name", "name_local", "area", "hours", "booking", "entry", "price_range",
                     "tabelog_rating", "guide", "cuisine", "station", "address_local", "coords", "coords_precision")):
    return {k: n[k] for k in keys if n.get(k) not in (None, "", [])}


def _route_km(items, start):
    km, prev = 0.0, start
    for it in items:
        if it.get("_c"):
            if prev:
                km += haversine_km(prev, it["_c"])
            prev = it["_c"]
    return km


def shortest_within_slots(items, start=None):
    """Same slots in the same order; inside a slot, greedily visit the nearest item next."""
    out, prev = [], start
    by_slot = {}
    for it in items:
        by_slot.setdefault(SLOT_ORDER.get(it.get("slot"), SLOT_ORDER["day"]), []).append(it)
    for _, group in sorted(by_slot.items()):
        rest = list(group)
        while rest:
            nxt = rest[0] if prev is None else min(
                rest, key=lambda it: haversine_km(prev, it["_c"]) if it.get("_c") else 10 ** 6)
            rest.remove(nxt)
            out.append(nxt)
            if nxt.get("_c"):
                prev = nxt["_c"]
    return out


def _meal_budget(n, slot):
    k = {"lunch": "budget_lunch", "dinner": "budget_dinner"}.get(slot)
    v = n.get(k) if k else None
    return tuple(v) if isinstance(v, list) and len(v) == 2 else None


def _fmt_windows(ws):
    return ", ".join(f"{hhmm(a)}–{hhmm(b % 1440)}" for a, b in ws)


def item_warnings(n, slot, sunset, day=None, hol=frozenset(), schema=SCHEMA, cur="JPY"):
    """Plan problems that are not hard errors: wrong time of day, a meal far above the budget cap."""
    out = []
    win = SLOT_WINDOWS.get(slot)
    windows = opening_windows(n, day, hol) if day is not None else None
    if windows is None:
        h = parse_hours(n.get("hours"), sunset)
        windows = [h] if isinstance(h, tuple) else None
    if win and windows is not None:
        if not windows:
            if not (day is not None and closures_on(n, day, hol)):
                out.append(f"{n.get('name')}: no opening hours on {WEEKDAYS[d(day).weekday()]} (check before going)")
        elif not any(a < win[1] and b > win[0] for a, b in windows):
            out.append(f"{n.get('name')}: planned for {slot} ({hhmm(win[0])}–{hhmm(win[1] % 1440)}) but open "
                       f"{_fmt_windows(windows)} that day")
    if n.get("type") == "restaurant" and slot in ("lunch", "dinner"):
        cap = strict_cap(cur, schema)
        r = _meal_budget(n, slot)
        if cap is not None and r and (r[0] or 0) > cap:
            other = "dinner" if slot == "lunch" else "lunch"
            o = _meal_budget(n, other)
            src = " (Tabelog)" if n.get("tabelog") or n.get("tabelog_list") else ""
            msg = f"{n.get('name')}: {slot} costs {money_range(r, cur, schema)} per person{src}"
            if o and o[1] is not None and o[1] <= cap:
                msg += f"; its {other} is {money_range(o, cur, schema)}"
            out.append(msg)
    return out


def day_view(nodes, paths, trip, day, profile=None, hol=None):
    hol = hol if hol is not None else holidays(nodes, trip.get("country"))
    date_ = d(day["date"])
    cur = currency_of(day, nodes)
    fx = fx_rates(profile)
    stay = nodes.get(day.get("stay")) if day.get("stay") else None
    start = coords(stay) if stay else None
    here = next((coords(nodes[paths[v]]) for v in day.get("visits") or [] if v in paths and coords(nodes[paths[v]])),
                None) or start or coords(nodes.get(paths.get(day.get("place")), {}))
    tz = utc_offset_hours(country_of(day, nodes))
    sunrise, sunset = sun_times(here[0], here[1], date_, tz) if here else (None, None)
    items, warnings = [], []
    for it in plan_items(day):
        n = nodes.get(it["id"])
        if not n:
            continue
        ncur = currency_of(n, nodes)
        est = it.get("cost") if it.get("cost") is not None else convert(estimate(n, it.get("slot"), cur=ncur), ncur, cur, fx)
        closed = closures_on(n, date_, hol) if n.get("type") in ("activity", "restaurant") else []
        row = {"slot": it.get("slot"), "id": n["id"], "type": n["type"], "name": n.get("name"),
               "est": est, "maps": maps_url(n, nodes, paths)}
        for k in ("name_local", "address_local", "hours", "booking", "area", "tabelog_rating", "guide", "cuisine",
                  "station"):
            if n.get(k) not in (None, "", []):
                row[k] = n[k]
        if it.get("note"):
            row["note"] = it["note"]
        if closed:
            row["closed"] = [{"rule": describe_rule(r), "partial": soft_closure(r)} if soft_closure(r)
                             else {"rule": describe_rule(r)} for r in closed]
        if n["type"] == "event":
            ed = edition_on(n, date_)
            if ed:
                row["edition"] = {"start": str(ed["start"]), "end": str(ed["end"])}
        w = item_warnings(n, it.get("slot"), sunset, date_, hol, cur=ncur)
        if w:
            row["warnings"] = w
            warnings.extend(w)
        c = coords(n)
        if c:
            row["coords"] = list(c)
        row["_c"] = c
        items.append(row)
    km = _route_km(items, start)
    prev = start
    for it in items:
        if it.get("_c"):
            if prev:
                it["km_from_prev"] = round(haversine_km(prev, it["_c"]), 1)
            prev = it["_c"]
    suggestion = None
    alt = shortest_within_slots(items, start)
    alt_km = _route_km(alt, start)
    if [i["id"] for i in alt] != [i["id"] for i in items] and km - alt_km >= 1.0 and alt_km <= 0.85 * km:
        suggestion = {"order": [i["id"] for i in alt], "km": round(alt_km, 1), "saves_km": round(km - alt_km, 1)}
        warnings.append(f"a shorter order saves ~{suggestion['saves_km']} km: " + " → ".join(i["name"] for i in alt))
    for it in items:
        it.pop("_c", None)
    places = allowed_places(trip, day)
    events = []
    for eid in events_on(nodes, places, date_):
        e, ed = nodes[eid], edition_on(nodes[eid], date_)
        events.append({"id": eid, "name": e.get("name"), "start": str(ed["start"]), "end": str(ed["end"]),
                       "in_plan": any(i["id"] == eid for i in items)})
    est_known = [i["est"] for i in items if i.get("est") is not None]
    city_node = nodes.get(paths.get(day.get("place")), {})
    transport = city_node.get("local_transport_day")
    if transport:
        est_known.append(transport)
    nights = trip_nights(trip)
    prev_stop = nights.get(date_ - timedelta(days=1))
    tonight = nights.get(date_)
    hotel_moves = {}
    if prev_stop and prev_stop.get("accommodation") and (not tonight or tonight is not prev_stop):
        h = nodes.get(prev_stop["accommodation"], {})
        hotel_moves["check_out"] = {"hotel": h.get("name"), "time": h.get("check_out")}
    if tonight and tonight.get("accommodation") and (not prev_stop or prev_stop is not tonight):
        h = nodes.get(tonight["accommodation"], {})
        hotel_moves["check_in"] = {"hotel": h.get("name"), "time": h.get("check_in")}
    spent = sum(int(x.get("amount") or 0) for x in day.get("expenses") or [] if isinstance(x, dict))
    view = {"id": day["id"], "date": str(date_), "weekday": WEEKDAYS[date_.weekday()],
            "holiday": date_ in hol, "place": day.get("place"),
            "city": nodes.get(paths.get(day.get("place")), {}).get("name"),
            "title": day.get("title"),
            "stay": summary(stay, ("id", "name", "name_local", "address_local", "coords", "check_in", "check_out",
                                   "phone"))
            if stay else None, **hotel_moves,
            "visits": day.get("visits") or [],
            "sunrise": hhmm(sunrise) if sunrise is not None else None,
            "sunset": hhmm(sunset) if sunset is not None else None,
            "items": items, "events": events, "straight_line_km": round(km, 1),
            "suggestion": suggestion, "warnings": warnings,
            "currency": cur, "est": sum(est_known), "local_transport": transport,
            "unpriced": [i["id"] for i in items if i.get("est") is None],
            "budget": daily_budget(profile, cur),
            "spent": spent if day.get("expenses") else None,
            "done": day.get("done") or [], "expenses": day.get("expenses") or []}
    return view


def deadlines(nodes, trip, day_views, schema=SCHEMA):
    """Ticket sale openings of events relevant to the trip + booking reminders for planned items."""
    out = []
    a, b = d(trip["start"]), d(trip["end"])
    places = trip_places(trip, nodes)
    seen = set()
    for eid, e in sorted(nodes.items()):
        if e.get("type") != "event" or e.get("place") not in places:
            continue
        for ed in editions_overlapping(e, a, b):
            for kind in ("presale", "on_sale"):
                when = ed.get(kind)
                if not when or (eid, kind) in seen:
                    continue
                seen.add((eid, kind))
                out.append({"kind": kind, "id": eid, "name": e.get("name"),
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
            lead = n["book_ahead_days"] if n.get("book_ahead_days") is not None else defaults.get(booking, 7)
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
    cur = currency_of(trip, nodes)
    fx = fx_rates(profile)

    def total(k):
        vals = [convert(v[k] or 0, v["currency"], cur, fx) for v in views]
        return None if any(x is None for x in vals) else sum(vals)

    budget = daily_budget(profile, cur)
    totals = {"currency": cur, "est": total("est"),
              "budget": budget * len(views) if budget else None,
              "spent": total("spent"),
              "days_over_budget": [v["date"] for v in views if v["budget"] and v["est"] > v["budget"]]}
    if totals["est"] is not None and fx.get(cur):
        totals["est_eur"] = round(totals["est"] / fx[cur])
    a, b = d(trip["start"]), d(trip["end"])
    places = trip_places(trip, nodes)
    events = []
    for eid, e in sorted(nodes.items()):
        if e.get("type") == "event" and e.get("place") in places:
            for ed in editions_overlapping(e, a, b):
                on = [v["date"] for v in views if any(x["id"] == eid for x in v["events"])]
                events.append({"id": eid, "name": e.get("name"), "place": e.get("place"), "start": str(ed["start"]),
                               "end": str(ed["end"]), "our_days": on,
                               "in_plan": [v["date"] for v in views if any(i["id"] == eid for i in v["items"])]})
    events.sort(key=lambda x: (x["start"], x["id"]))
    country = nodes.get(trip.get("country")) or {}
    return {"trip": trip["id"], "name": trip.get("name"), "start": str(a), "end": str(b), "tz": country.get("tz"),
            "nights": nights, "currency": cur,
            "budget": {"daily": budget, "currency": cur, **((profile or {}).get("budget") or {})},
            "totals": totals, "events": events, "deadlines": deadlines(nodes, trip, views), "days": views}


def now_utc():
    return datetime.now(timezone.utc)
