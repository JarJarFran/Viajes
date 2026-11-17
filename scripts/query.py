"""Query the travel graph. Compact JSON lines by default (agent-friendly), --format md for tables.

Examples:
  query.py restaurants --city osaka --area namba --min-rating 3.5 --max-yen 4999 --meal lunch
  query.py near --id tokyo-sensoji --type restaurant --km 0.8
  query.py activities --city kyoto --entry free --tag top50 --open-on 2027-01-02
  query.py day --trip 2026-japan --date 2027-01-10
  query.py budget --trip 2026-japan
  query.py deadlines --trip 2026-japan
  query.py closures --trip 2026-japan
  query.py stale --months 12 --trip 2026-japan
  query.py affinity
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (REPO, SCHEMA, area_of, cheapest_meal_yen, city_children, closures_on, coords, d,  # noqa: E402
                    describe_rule, edition_on, editions, editions_overlapping, haversine_km, holidays, load_graph,
                    restaurant_range, strict_restaurants)
from tripplan import load_profile, trip_view  # noqa: E402

nodes, paths, edges = load_graph(REPO)


def emit(rows, fields, fmt):
    if fmt == "json":
        for r in rows:
            print(json.dumps({k: r.get(k) for k in fields if r.get(k) not in (None, [], "")},
                             ensure_ascii=False, separators=(",", ":"), default=str))
        return
    if not rows:
        print("(no results)")
        return
    cols = [f for f in fields if any(r.get(f) not in (None, [], "") for r in rows)]
    print("| " + " | ".join(cols) + " |")
    print("|" + "|".join(["---"] * len(cols)) + "|")
    for r in rows:
        print("| " + " | ".join(_cell(r.get(c)) for c in cols) + " |")


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(map(str, v))
    return str(v).replace("|", "/")


def city_path(city):
    if city in paths:
        return city
    return next((p for p in paths if p.endswith("/" + city)), None) or sys.exit(f"unknown city {city}")


def area_match(n, q):
    """Match an area id or a substring of its name/aliases or of the node's area_detail."""
    q = q.lower()
    aid = area_of(n["id"], nodes, edges)
    a = nodes.get(aid) or {}
    hay = [aid or "", a.get("name", ""), n.get("area_detail", "")] + list(a.get("aliases") or [])
    return any(q in str(h).lower() for h in hay)


def with_area(n):
    r = dict(n)
    aid = area_of(n["id"], nodes, edges)
    if aid:
        r["area"] = nodes[aid]["name"]
    return r


def _hi(rng):
    return rng[1] if rng and rng[1] is not None else 10 ** 9


def get_trip(tid):
    t = nodes.get(tid)
    if not t or t.get("type") != "trip":
        sys.exit(f"unknown trip {tid}")
    return t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    fmt = argparse.ArgumentParser(add_help=False)
    fmt.add_argument("--format", choices=["json", "md"], default="json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats", parents=[fmt])
    p = sub.add_parser("node", parents=[fmt]); p.add_argument("--id", required=True); p.add_argument("--body", action="store_true")
    p = sub.add_parser("restaurants", parents=[fmt])
    p.add_argument("--city", required=True); p.add_argument("--area"); p.add_argument("--cuisine"); p.add_argument("--tag")
    p.add_argument("--min-rating", type=float); p.add_argument("--max-price", choices=SCHEMA["vocabularies"]["price_range"])
    p.add_argument("--max-yen", type=int, help="some meal (or --meal) at or under this per person")
    p.add_argument("--meal", choices=["lunch", "dinner"]); p.add_argument("--near"); p.add_argument("--km", type=float, default=1.0)
    p.add_argument("--sort", choices=["rating", "price", "name", "distance"], default="rating"); p.add_argument("--limit", type=int)
    p = sub.add_parser("activities", parents=[fmt])
    p.add_argument("--city", required=True); p.add_argument("--entry", choices=SCHEMA["vocabularies"]["entry"])
    p.add_argument("--tag"); p.add_argument("--booking", choices=SCHEMA["vocabularies"]["booking"]); p.add_argument("--category")
    p.add_argument("--area"); p.add_argument("--free", action="store_true"); p.add_argument("--open-on", help="YYYY-MM-DD: drop places fully closed that day")
    p = sub.add_parser("events", parents=[fmt]); p.add_argument("--city"); p.add_argument("--trip"); p.add_argument("--on-date")
    p = sub.add_parser("hotels", parents=[fmt]); p.add_argument("--city", required=True); p.add_argument("--area")
    p = sub.add_parser("routes", parents=[fmt]); p.add_argument("--city"); p.add_argument("--to")
    p = sub.add_parser("areas", parents=[fmt]); p.add_argument("--city", required=True)
    p = sub.add_parser("cluster", parents=[fmt]); p.add_argument("--id", required=True)
    p = sub.add_parser("near", parents=[fmt]); p.add_argument("--id", required=True)
    p.add_argument("--type", choices=["restaurant", "activity", "hotel", "event", "area"]); p.add_argument("--km", type=float, default=1.0)
    p.add_argument("--limit", type=int, default=15)
    p = sub.add_parser("day", parents=[fmt]); p.add_argument("--trip", required=True); p.add_argument("--date")
    p = sub.add_parser("plan", parents=[fmt])
    p.add_argument("--city", required=True); p.add_argument("--area"); p.add_argument("--min-rating", type=float, default=3.5)
    p.add_argument("--max-yen", type=int, default=4999); p.add_argument("--cuisine"); p.add_argument("--with-activities", action="store_true")
    p = sub.add_parser("shortlist", parents=[fmt]); p.add_argument("--city", required=True)
    p = sub.add_parser("budget", parents=[fmt]); p.add_argument("--trip", required=True)
    p = sub.add_parser("deadlines", parents=[fmt]); p.add_argument("--trip", required=True)
    p.add_argument("--upcoming", action="store_true", help="only from today on")
    p = sub.add_parser("closures", parents=[fmt]); p.add_argument("--trip"); p.add_argument("--id")
    p.add_argument("--from", dest="since"); p.add_argument("--to", dest="until")
    p = sub.add_parser("stale", parents=[fmt]); p.add_argument("--months", type=int, default=12)
    p.add_argument("--trip", help="only nodes planned in this trip"); p.add_argument("--type")
    sub.add_parser("affinity", parents=[fmt])
    a = ap.parse_args()
    f = a.format

    if a.cmd == "stats":
        from collections import Counter
        counts = Counter(n.get("type") for n in nodes.values())
        print(json.dumps({"counts": dict(sorted(counts.items())), "nodes": len(nodes), "edges": len(edges),
                          "restaurants_strict": len(strict_restaurants(nodes)),
                          "with_coords": sum(1 for n in nodes.values() if n.get("coords"))}, ensure_ascii=False))

    elif a.cmd == "node":
        n = nodes.get(a.id) or sys.exit(f"unknown id {a.id}")
        out = {k: v for k, v in n.items() if not k.startswith("_")}
        if a.body:
            out["body"] = n["_body"].strip()
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))

    elif a.cmd in ("restaurants", "plan"):
        cp = city_path(a.city)
        rows = [nodes[x] for x in city_children(nodes, cp, ("restaurant",))]
        if a.area:
            rows = [r for r in rows if area_match(r, a.area)]
        if a.cuisine:
            rows = [r for r in rows if a.cuisine.lower() in (r.get("cuisine") or "").lower()]
        if getattr(a, "tag", None):
            rows = [r for r in rows if a.tag in (r.get("tags") or [])]
        if a.min_rating is not None:
            rows = [r for r in rows if r.get("tabelog_rating") is not None and float(r["tabelog_rating"]) >= a.min_rating]
        meal = getattr(a, "meal", None)
        if getattr(a, "max_price", None):
            cap = SCHEMA["price_range_yen"][a.max_price][1] or 10 ** 9
            rows = [r for r in rows if _hi(restaurant_range(r, meal)) <= cap]
        if a.max_yen is not None:
            if meal:
                rows = [r for r in rows if _hi(restaurant_range(r, meal)) <= a.max_yen]
            else:
                rows = [r for r in rows if (cheapest_meal_yen(r) or 10 ** 9) <= a.max_yen]
        origin = coords(nodes[a.near]) if getattr(a, "near", None) and a.near in nodes else None
        out = []
        for r in rows:
            x = with_area(r)
            rng = restaurant_range(r, meal)
            x["yen"] = f"{rng[0] or ''}-{rng[1] or ''}" if rng else None
            if origin and coords(r):
                x["km"] = round(haversine_km(origin, coords(r)), 2)
            out.append(x)
        if origin:
            out = [x for x in out if x.get("km") is not None and x["km"] <= a.km]
        sort = getattr(a, "sort", "rating")
        key = {"rating": lambda r: -float(r.get("tabelog_rating") or 0), "price": lambda r: cheapest_meal_yen(r) or 0,
               "name": lambda r: r.get("name", ""), "distance": lambda r: r.get("km", 99)}[sort if not origin or sort != "rating" else "distance"]
        out.sort(key=key)
        if getattr(a, "limit", None):
            out = out[:a.limit]
        if a.cmd == "plan" and a.with_activities:
            acts = [with_area(nodes[x]) for x in city_children(nodes, cp, ("activity",))
                    if {"top50", "top100"} & set(nodes[x].get("tags") or [])]
            print("# activities (top50/top100)")
            emit(sorted(acts, key=lambda r: r["name"]), ["id", "name", "area", "category", "entry", "cost_yen", "hours", "booking"], f)
            print("# restaurants")
        emit(out, ["id", "name", "cuisine", "area", "area_detail", "price_range", "yen", "tabelog_rating", "station", "km", "tags"], f)

    elif a.cmd == "activities":
        rows = [nodes[x] for x in city_children(nodes, city_path(a.city), ("activity",))]
        if a.free:
            a.entry = "free"
        for k in ("entry", "booking"):
            if getattr(a, k):
                rows = [r for r in rows if r.get(k) == getattr(a, k)]
        if a.tag:
            rows = [r for r in rows if a.tag in (r.get("tags") or [])]
        if a.category:
            rows = [r for r in rows if a.category.lower() in (r.get("category") or "").lower()]
        if a.area:
            rows = [r for r in rows if area_match(r, a.area)]
        if a.open_on:
            hol = holidays(nodes, "japan")
            rows = [r for r in rows if not any(not c.get("partial") for c in closures_on(r, d(a.open_on), hol))]
        emit([with_area(r) for r in sorted(rows, key=lambda r: r["name"])],
             ["id", "name", "area", "category", "entry", "cost_yen", "tags", "hours", "booking", "duration_hours"], f)

    elif a.cmd == "events":
        rows = []
        for e in (n for n in nodes.values() if n.get("type") == "event"):
            if a.city and e.get("place") != city_path(a.city):
                continue
            eds = editions(e)
            if a.trip:
                t = get_trip(a.trip)
                places = {s.get("place") for s in t.get("stops") or []}
                eds = editions_overlapping(e, d(t["start"]), d(t["end"])) if e.get("place") in places else []
            if a.on_date:
                ed = edition_on(e, a.on_date)
                eds = [ed] if ed else []
            for ed in eds:
                rows.append(dict(e, start=str(ed["start"]), end=str(ed["end"]), on_sale=ed.get("on_sale")))
        rows.sort(key=lambda r: (r["start"], r["id"]))
        emit(rows, ["id", "name", "place", "start", "end", "on_sale", "entry", "cost_yen", "recurrence"], f)

    elif a.cmd == "hotels":
        rows = [nodes[x] for x in city_children(nodes, city_path(a.city), ("hotel",))]
        if a.area:
            rows = [r for r in rows if area_match(r, a.area)]
        emit([with_area(r) for r in rows], ["id", "name", "area", "area_detail", "price_range", "name_ja", "link"], f)

    elif a.cmd == "routes":
        rows = [n for n in nodes.values() if n.get("type") == "route"]
        if a.city:
            cp = city_path(a.city)
            rows = [r for r in rows if cp in (r.get("origin"), r.get("destination"))]
        if a.to:
            cp = city_path(a.to)
            rows = [r for r in rows if cp in (r.get("origin"), r.get("destination"))]
        emit(sorted(rows, key=lambda r: r["id"]), ["id", "name", "mode", "duration_hours", "price_yen", "booking", "approx_cost"], f)

    elif a.cmd == "areas":
        rows = [nodes[x] for x in city_children(nodes, city_path(a.city), ("area",))]
        cnt = defaultdict(int)
        for n in nodes.values():
            aid = area_of(n["id"], nodes, edges) if n.get("type") in ("activity", "restaurant", "hotel", "event") else None
            if aid:
                cnt[aid] += 1
        emit([dict(r, nodes=cnt[r["id"]]) for r in rows], ["id", "name", "nodes", "coords", "aliases"], f)

    elif a.cmd == "cluster":
        n = nodes.get(a.id) or sys.exit(f"unknown id {a.id}")
        ids = list(dict.fromkeys((n.get("near") or []) + [e["to"] for e in edges if e["from"] == a.id and e["rel"] == "nearby"
                                                          and nodes[e["to"]]["type"] == "activity"]))
        rows = [with_area(n)] + [with_area(nodes[x]) for x in ids if x in nodes]
        for r in rows[1:]:
            if coords(n) and coords(r):
                r["km"] = round(haversine_km(coords(n), coords(r)), 2)
        emit(rows, ["id", "name", "type", "area", "km", "entry", "cost_yen", "hours", "booking"], f)

    elif a.cmd == "near":
        n = nodes.get(a.id) or sys.exit(f"unknown id {a.id}")
        c = coords(n) or sys.exit(f"{a.id} has no coords")
        rows = []
        for x in nodes.values():
            if x["id"] == a.id or not coords(x) or x.get("type") in ("city", "region", "country", "day", "trip"):
                continue
            if a.type and x.get("type") != a.type:
                continue
            km = haversine_km(c, coords(x))
            if km <= a.km:
                rows.append(dict(with_area(x), km=round(km, 2)))
        rows.sort(key=lambda r: r["km"])
        emit(rows[:a.limit], ["id", "name", "type", "km", "area", "cuisine", "price_range", "tabelog_rating", "entry", "coords_precision"], f)

    elif a.cmd == "day":
        t = get_trip(a.trip)
        view = trip_view(nodes, paths, t, load_profile(REPO))
        if a.date:
            v = next((x for x in view["days"] if x["date"] == a.date), None) or sys.exit(f"no day {a.date} in {a.trip}")
            print(json.dumps(v, ensure_ascii=False, indent=1, default=str))
        else:
            emit([dict(v, plan=[i["id"] for i in v["items"]]) for v in view["days"]],
                 ["date", "weekday", "city", "title", "plan", "est_yen"], f)

    elif a.cmd == "shortlist":
        cid = paths.get(city_path(a.city))
        fp = os.path.join(REPO, "exports", "shortlists", f"{cid}.json")
        print(open(fp, encoding="utf-8").read() if os.path.exists(fp) else "run scripts/sync.py first")

    elif a.cmd == "budget":
        view = trip_view(nodes, paths, get_trip(a.trip), load_profile(REPO))
        b = view["budget"].get("daily_yen")
        rows = [{"date": v["date"], "city": v["city"], "est_yen": v["est_yen"], "budget_yen": b,
                 "over": (v["est_yen"] - b) if b and v["est_yen"] > b else None, "spent_yen": v["spent_yen"],
                 "unpriced": v["unpriced"]} for v in view["days"]]
        emit(rows, ["date", "city", "est_yen", "budget_yen", "over", "spent_yen", "unpriced"], f)
        print(json.dumps({"totals": view["totals"], "eur_jpy": view["budget"].get("eur_jpy")}, default=str))

    elif a.cmd == "deadlines":
        view = trip_view(nodes, paths, get_trip(a.trip), load_profile(REPO))
        rows = view["deadlines"]
        if a.upcoming:
            rows = [r for r in rows if r["date"] >= date.today().isoformat()]
        emit(rows, ["date", "when", "kind", "id", "name", "for", "booking", "note"], f)

    elif a.cmd == "closures":
        if a.trip:
            view = trip_view(nodes, paths, get_trip(a.trip), load_profile(REPO))
            rows = [{"date": v["date"], "weekday": v["weekday"], "id": i["id"], "name": i["name"],
                     "rule": "; ".join(c["rule"] for c in i["closed"]),
                     "partial": "; ".join(c.get("partial") or "" for c in i["closed"]) or None}
                    for v in view["days"] for i in v["items"] if i.get("closed")]
            emit(rows, ["date", "weekday", "id", "name", "rule", "partial"], f)
        elif a.id:
            n = nodes.get(a.id) or sys.exit(f"unknown id {a.id}")
            hol = holidays(nodes, "japan")
            from datetime import timedelta
            x, end = d(a.since or date.today()), d(a.until or (d(a.since or date.today()) + timedelta(days=60)))
            rows = []
            while x <= end:
                for r in closures_on(n, x, hol):
                    rows.append({"date": str(x), "rule": describe_rule(r), "partial": r.get("partial")})
                x += timedelta(days=1)
            emit(rows, ["date", "rule", "partial"], f)
        else:
            sys.exit("closures needs --trip or --id")

    elif a.cmd == "stale":
        today = date.today()
        ids = None
        if a.trip:
            view = trip_view(nodes, paths, get_trip(a.trip), load_profile(REPO))
            ids = {i["id"] for v in view["days"] for i in v["items"]}
        rows = []
        for n in nodes.values():
            if n.get("type") not in ("activity", "event", "restaurant", "hotel", "route"):
                continue
            if ids is not None and n["id"] not in ids:
                continue
            if a.type and n["type"] != a.type:
                continue
            v = n.get("verified")
            if v is None:
                rows.append({"id": n["id"], "type": n["type"], "verified": None, "age_months": None})
                continue
            y, m = int(str(v)[:4]), int(str(v)[5:7])
            age = (today.year - y) * 12 + today.month - m
            if age >= a.months:
                rows.append({"id": n["id"], "type": n["type"], "verified": str(v), "age_months": age})
        rows.sort(key=lambda r: (r["verified"] is not None, r["verified"] or "", r["id"]))
        emit(rows, ["id", "type", "verified", "age_months"], f)

    elif a.cmd == "affinity":
        groups = defaultdict(list)
        for day in (n for n in nodes.values() if n.get("type") == "day"):
            for x in day.get("done") or []:
                n = nodes.get(x.get("id"))
                if not n or x.get("rating") is None:
                    continue
                r = x["rating"]
                groups[("type", n["type"])].append(r)
                if n.get("category"):
                    groups[("category", n["category"])].append(r)
                if n.get("cuisine"):
                    groups[("cuisine", n["cuisine"].split(",")[0].strip())].append(r)
                for t in n.get("tags") or []:
                    groups[("tag", t)].append(r)
                groups[("city", n.get("place", n.get("origin", "")).split("/")[-1])].append(r)
        rows = [{"by": k[0], "value": k[1], "n": len(v), "avg": round(sum(v) / len(v), 2)} for k, v in groups.items()]
        rows.sort(key=lambda r: (-r["avg"], -r["n"]))
        if not rows:
            print("(no ratings yet — log them with scripts/log.py done ... --rating 1-5)")
        emit(rows, ["by", "value", "n", "avg"], f)


if __name__ == "__main__":
    main()
