import argparse, json, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import REPO, SCHEMA, load_graph, city_children, strict_restaurants, d, PRICE_MAX_YEN

nodes, paths, edges = load_graph()


def emit(rows, fields, fmt):
    if fmt == "json":
        for r in rows:
            print(json.dumps({k: r.get(k) for k in fields if r.get(k) is not None}, ensure_ascii=False, separators=(",", ":"), default=str))
    else:
        if not rows:
            print("(no results)")
            return
        cols = [f for f in fields if any(r.get(f) is not None for r in rows)]
        print("| " + " | ".join(cols) + " |")
        print("|" + "|".join(["---"] * len(cols)) + "|")
        for r in rows:
            print("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")


def by_city(city):
    cpath = next((p for p in paths if p.endswith("/" + city)), None)
    if not cpath:
        cpath = city if city in paths else None
    return cpath


def main():
    ap = argparse.ArgumentParser(description="Query the travel knowledge graph (agent-friendly, compact output)")
    fmt = argparse.ArgumentParser(add_help=False)
    fmt.add_argument("--format", choices=["json", "md"], default="json", help="json = JSON lines (default), md = table")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stats", parents=[fmt])

    p = sub.add_parser("node", parents=[fmt])
    p.add_argument("--id", required=True)
    p.add_argument("--body", action="store_true")

    p = sub.add_parser("restaurants", parents=[fmt])
    p.add_argument("--city", required=True)
    p.add_argument("--area")
    p.add_argument("--cuisine")
    p.add_argument("--tag")
    p.add_argument("--min-rating", type=float)
    p.add_argument("--max-price", choices=["¥", "¥¥", "¥¥¥", "¥¥¥¥"])
    p.add_argument("--max-yen", type=int)
    p.add_argument("--sort", choices=["rating", "price", "name"], default="rating")

    p = sub.add_parser("activities", parents=[fmt])
    p.add_argument("--city", required=True)
    p.add_argument("--entry", choices=SCHEMA["vocabularies"]["entry"])
    p.add_argument("--tag")
    p.add_argument("--booking", choices=SCHEMA["vocabularies"]["booking"])
    p.add_argument("--category")
    p.add_argument("--free", action="store_true", help="shortcut for --entry free")

    p = sub.add_parser("events", parents=[fmt])
    p.add_argument("--city")
    p.add_argument("--trip")
    p.add_argument("--on-date")

    p = sub.add_parser("hotels", parents=[fmt])
    p.add_argument("--city", required=True)
    p.add_argument("--area")

    p = sub.add_parser("cluster", parents=[fmt])
    p.add_argument("--id", required=True)

    p = sub.add_parser("day", parents=[fmt])
    p.add_argument("--trip", required=True)
    p.add_argument("--date")

    p = sub.add_parser("plan", parents=[fmt])
    p.add_argument("--city", required=True)
    p.add_argument("--area")
    p.add_argument("--min-rating", type=float, default=3.5)
    p.add_argument("--max-yen", type=int, default=4999)
    p.add_argument("--cuisine")
    p.add_argument("--with-activities", action="store_true")

    p = sub.add_parser("shortlist", parents=[fmt])
    p.add_argument("--city", required=True)

    args = ap.parse_args()

    if args.cmd == "stats":
        from collections import Counter
        counts = Counter(n.get("type") for n in nodes.values())
        print(json.dumps({"counts": dict(sorted(counts.items())), "nodes": len(nodes), "edges": len(edges),
                          "restaurants_strict": len(strict_restaurants(nodes))}, ensure_ascii=False))
        per_city = {}
        for nid in strict_restaurants(nodes):
            c = nodes[nid]["place"].split("/")[-1]
            per_city[c] = per_city.get(c, 0) + 1
        print(json.dumps({"strict_per_city": per_city}, ensure_ascii=False))

    elif args.cmd == "node":
        n = nodes.get(args.id)
        if not n:
            sys.exit(f"unknown id {args.id}")
        out = {k: v for k, v in n.items() if not k.startswith("_")}
        if args.body:
            out["body"] = n["_body"].strip()
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))

    elif args.cmd == "restaurants":
        cpath = by_city(args.city)
        rows = [nodes[nid] for nid in city_children(nodes, cpath)] if cpath else []
        rows = [r for r in rows if r.get("type") == "restaurant"]
        if args.area:
            rows = [r for r in rows if args.area.lower() in (r.get("area") or "").lower()]
        if args.cuisine:
            rows = [r for r in rows if args.cuisine.lower() in (r.get("cuisine") or "").lower()]
        if args.tag:
            rows = [r for r in rows if args.tag in (r.get("tags") or [])]
        if args.min_rating is not None:
            rows = [r for r in rows if r.get("tabelog_rating") is not None and float(r["tabelog_rating"]) >= args.min_rating]
        if args.max_price:
            cap = PRICE_MAX_YEN[args.max_price]
            rows = [r for r in rows if PRICE_MAX_YEN.get(r.get("price_range"), 10**9) <= cap]
        if args.max_yen is not None:
            rows = [r for r in rows if PRICE_MAX_YEN.get(r.get("price_range"), 10**9) <= args.max_yen]
        key = {"rating": lambda r: -(r.get("tabelog_rating") or 0), "price": lambda r: PRICE_MAX_YEN.get(r.get("price_range"), 0), "name": lambda r: r.get("name", "")}[args.sort]
        rows.sort(key=key)
        emit(rows, ["id", "name", "cuisine", "area", "price_range", "tabelog_rating", "tags"], args.format)

    elif args.cmd == "activities":
        cpath = by_city(args.city)
        rows = [nodes[nid] for nid in city_children(nodes, cpath)] if cpath else []
        rows = [r for r in rows if r.get("type") == "activity"]
        if args.free:
            args.entry = "free"
        if args.entry:
            rows = [r for r in rows if r.get("entry") == args.entry]
        if args.tag:
            rows = [r for r in rows if args.tag in (r.get("tags") or [])]
        if args.booking:
            rows = [r for r in rows if r.get("booking") == args.booking]
        if args.category:
            rows = [r for r in rows if args.category.lower() in (r.get("category") or "").lower()]
        rows.sort(key=lambda r: r.get("name", ""))
        emit(rows, ["id", "name", "category", "entry", "tags", "approx_cost", "hours", "booking", "duration_hours"], args.format)

    elif args.cmd == "events":
        rows = [n for n in nodes.values() if n.get("type") == "event"]
        if args.city:
            cpath = by_city(args.city)
            rows = [r for r in rows if r.get("place") == cpath]
        if args.trip:
            t = nodes.get(args.trip)
            if not t:
                sys.exit(f"unknown trip {args.trip}")
            ts, te = d(t["start"]), d(t["end"])
            rows = [r for r in rows if d(r["end"]) >= ts and d(r["start"]) <= te]
        if args.on_date:
            dd = d(args.on_date)
            rows = [r for r in rows if d(r["start"]) <= dd <= d(r["end"])]
        rows.sort(key=lambda r: r.get("start", ""))
        emit(rows, ["id", "name", "place", "start", "end", "entry", "approx_cost", "on_sale", "tags"], args.format)

    elif args.cmd == "hotels":
        cpath = by_city(args.city)
        rows = [nodes[nid] for nid in city_children(nodes, cpath)] if cpath else []
        rows = [r for r in rows if r.get("type") == "hotel"]
        if args.area:
            rows = [r for r in rows if args.area.lower() in (r.get("area") or "").lower()]
        emit(rows, ["id", "name", "area", "price_range", "link"], args.format)

    elif args.cmd == "cluster":
        n = nodes.get(args.id)
        if not n:
            sys.exit(f"unknown id {args.id}")
        near = n.get("near") or []
        rows = [n] + [nodes[x] for x in near if x in nodes]
        fields = ["id", "name", "type", "place", "entry", "tags", "approx_cost", "hours", "booking", "area", "price_range", "tabelog_rating"]
        emit(rows, fields, args.format)

    elif args.cmd == "day":
        t = nodes.get(args.trip)
        if not t:
            sys.exit(f"unknown trip {args.trip}")
        days = t.get("days") or []
        if args.date:
            did = f"day-{args.date}"
            if did not in nodes:
                sys.exit(f"no day node {did}")
            dn = nodes[did]
            out = {k: v for k, v in dn.items() if not k.startswith("_")}
            out["plan_detail"] = [{k: nodes[x].get(k) for k in ("id", "name", "type", "entry", "tags", "approx_cost", "price_range", "tabelog_rating", "area", "hours", "booking")} for x in dn.get("plan", []) if x in nodes]
            out["events_detail"] = [{k: nodes[x].get(k) for k in ("id", "name", "start", "end", "entry", "approx_cost")} for x in dn.get("events", []) if x in nodes]
            print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        else:
            rows = [nodes[x] for x in days if x in nodes]
            emit(rows, ["id", "date", "place", "stay", "plan", "events"], args.format)

    elif args.cmd == "plan":
        cpath = by_city(args.city)
        rows = [nodes[nid] for nid in city_children(nodes, cpath)] if cpath else []
        rows = [r for r in rows if r.get("type") == "restaurant"]
        if args.area:
            rows = [r for r in rows if args.area.lower() in (r.get("area") or "").lower()]
        if args.cuisine:
            rows = [r for r in rows if args.cuisine.lower() in (r.get("cuisine") or "").lower()]
        rows = [r for r in rows if r.get("tabelog_rating") is not None and float(r["tabelog_rating"]) >= args.min_rating
                and PRICE_MAX_YEN.get(r.get("price_range"), 10**9) <= args.max_yen]
        rows.sort(key=lambda r: -float(r.get("tabelog_rating") or 0))
        if args.with_activities:
            acts = [nodes[nid] for nid in city_children(nodes, cpath)
                    if nodes[nid].get("type") == "activity" and ({"top50", "top100"} & set(nodes[nid].get("tags") or []))]
            acts.sort(key=lambda r: r.get("name", ""))
            print("# activities (top50/top100)")
            emit(acts, ["id", "name", "category", "entry", "tags", "approx_cost", "hours", "booking"], args.format)
            print("# restaurants (min-rating %.2f, max-yen %d)" % (args.min_rating, args.max_yen))
        emit(rows, ["id", "name", "cuisine", "area", "price_range", "tabelog_rating"], args.format)

    elif args.cmd == "shortlist":
        cpath = by_city(args.city)
        cid = paths.get(cpath)
        fp = f"{REPO}/exports/shortlists/{cid}.json"
        if not __import__("os").path.exists(fp):
            sys.exit("run `python3 scripts/sync.py` first to build exports/")
        print(open(fp, encoding="utf-8").read())


if __name__ == "__main__":
    main()
