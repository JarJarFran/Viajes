"""Validate the travel graph against schema.yaml: parse errors, duplicate ids, unknown keys,
vocabularies, references, file locations, trip/day consistency, plan feasibility (city, event
dates, closures) and relative Markdown links. Exit 1 on errors; warnings never fail.

    python3 scripts/validate_graph.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (PLANNABLE, REPO, SCHEMA, allowed_places, closures_on, coords, d, day_id,  # noqa: E402
                    describe_rule, edition_on, editions, expected_day, expected_file, haversine_km, holidays,
                    load_graph, load_schema, node_places, plan_items, read, rel, strict_restaurants, trip_day_ids,
                    trip_window, WEEKDAYS)

MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
VERIFIED_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
RANGE_MD = re.compile(r"^(\d{2})-(\d{2})\.\.(\d{2})-(\d{2})$")


def _is_date(v):
    try:
        d(v)
        return True
    except (ValueError, TypeError):
        return False


def check_closed(rules, where, err):
    if not isinstance(rules, list):
        err(f"{where}: closed must be a list of rules (got {type(rules).__name__}); [] = no known closures")
        return
    kinds = ("weekly", "yearly", "dates", "specific", "irregular")
    for r in rules:
        if not isinstance(r, dict) or sum(k in r for k in kinds) != 1:
            err(f"{where}: closed rule {r!r} needs exactly one of {kinds}")
            continue
        extra = set(r) - set(kinds) - {"holiday_shift", "nth", "partial", "note"}
        if extra:
            err(f"{where}: closed rule has unknown keys {sorted(extra)}")
        if "weekly" in r:
            if not r["weekly"] or any(x not in WEEKDAYS for x in r["weekly"]):
                err(f"{where}: closed.weekly must use {WEEKDAYS}")
            if any(not isinstance(x, int) or not 1 <= x <= 5 for x in r.get("nth") or []):
                err(f"{where}: closed.nth must be 1-5")
        if "yearly" in r:
            m = RANGE_MD.match(str(r["yearly"]))
            if not m or not (1 <= int(m[1]) <= 12 and 1 <= int(m[3]) <= 12 and 1 <= int(m[2]) <= 31 and 1 <= int(m[4]) <= 31):
                err(f"{where}: closed.yearly must be MM-DD..MM-DD (got {r['yearly']})")
        if "dates" in r:
            parts = str(r["dates"]).split("..")
            if len(parts) != 2 or not all(_is_date(p) for p in parts) or d(parts[0]) > d(parts[1]):
                err(f"{where}: closed.dates must be YYYY-MM-DD..YYYY-MM-DD (got {r['dates']})")
        if "specific" in r and (not isinstance(r["specific"], list) or not all(_is_date(x) for x in r["specific"])):
            err(f"{where}: closed.specific must be a list of dates")


def check_links(root, err):
    for base in ("destinations", "trips", "_templates", "."):
        top = os.path.join(root, base)
        for dirpath, dirs, files in os.walk(top):
            if base == ".":
                dirs[:] = []
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            for f in files:
                if not f.endswith(".md"):
                    continue
                fp = os.path.join(dirpath, f)
                text = re.sub(r"`[^`\n]*`", "", read(fp))
                for target in MD_LINK.findall(text):
                    if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                        continue
                    path = target.split("#")[0]
                    if path and not os.path.exists(os.path.normpath(os.path.join(dirpath, path))):
                        err(f"{rel(fp, root)}: broken link -> {target}")


def validate(root=REPO, today=None):
    schema = load_schema(root)
    errors, warnings = [], []
    nodes, paths, edges = load_graph(root, errors)
    err, warn = errors.append, warnings.append
    voc = schema["vocabularies"]
    id_re = re.compile(schema["id_pattern"])
    hol_cache = {}

    for nid, n in sorted(nodes.items()):
        fp, t = rel(n["_fp"], root), n.get("type")
        spec = schema["types"].get(t)
        if not id_re.match(nid):
            err(f"{fp}: id '{nid}' does not match {schema['id_pattern']}")
        if not spec:
            err(f"{fp}: unknown type {t!r}")
            continue
        for k in spec["required"]:
            if k not in n:
                err(f"{fp}: {t} missing required key '{k}'")
        for k in n:
            if not k.startswith("_") and k not in spec["keys"]:
                err(f"{fp}: unknown key '{k}' for type {t} (allowed: see schema.yaml)")
        for k, nspec in schema["nested"].items():
            for item in n.get(k) or [] if isinstance(n.get(k), list) else []:
                if isinstance(item, dict):
                    miss = [x for x in nspec["required"] if x not in item]
                    unk = [x for x in item if x not in nspec["keys"]]
                    if miss:
                        err(f"{fp}: {k} item {item} missing {miss}")
                    if unk:
                        err(f"{fp}: {k} item has unknown keys {unk}")
        exp = expected_file(n, nodes, paths, root)
        if exp and os.path.normpath(exp) != os.path.normpath(n["_fp"]):
            err(f"{fp}: should live at {rel(exp, root)}")
        for key, vocab in (("entry", "entry"), ("booking", "booking"), ("price_range", "price_range"),
                           ("status", "status"), ("mode", "mode"), ("coords_precision", "coords_precision")):
            if n.get(key) is not None and n[key] not in voc[vocab]:
                err(f"{fp}: {key}={n[key]!r} not in {voc[vocab]}")
        if t == "activity" and n.get("category") not in voc["category"]:
            err(f"{fp}: category={n.get('category')!r} not in {voc['category']}")
        for tag in n.get("tags") or []:
            if tag not in voc["tags"]:
                err(f"{fp}: tag {tag!r} not in vocabulary")
        if n.get("verified") is not None and not VERIFIED_RE.match(str(n["verified"])):
            err(f"{fp}: verified must be YYYY-MM or YYYY-MM-DD (got {n['verified']})")
        c = n.get("coords")
        if c is not None:
            if not (isinstance(c, list) and len(c) == 2 and all(isinstance(x, (int, float)) for x in c)
                    and -90 <= c[0] <= 90 and -180 <= c[1] <= 180):
                err(f"{fp}: coords must be [lat, lon]")
            elif t in ("restaurant", "hotel", "area"):
                city = nodes.get(paths.get(n.get("place")))
                if city and coords(city) and haversine_km(coords(city), coords(n)) > 40:
                    warn(f"{fp}: coords are {haversine_km(coords(city), coords(n)):.0f} km from {city['name']}")
        for k in ("cost_yen", "price_yen", "price_per_night_yen", "station_m", "book_ahead_days"):
            if n.get(k) is not None and (not isinstance(n[k], int) or n[k] < 0):
                err(f"{fp}: {k} must be a non-negative integer")
        for k in ("budget_lunch_yen", "budget_dinner_yen", "budget_yen"):
            v = n.get(k)
            if v is not None:
                ok = isinstance(v, list) and len(v) == 2 and all(x is None or isinstance(x, int) for x in v) \
                    and any(x is not None for x in v) and (None in v or v[0] <= v[1])
                if not ok:
                    err(f"{fp}: {k} must be [min, max] yen (one side may be null)")
        if n.get("tabelog_rating") is not None and not (0 <= float(n["tabelog_rating"]) <= 5):
            err(f"{fp}: tabelog_rating {n['tabelog_rating']} out of range")
        if t == "restaurant":
            if "/rstLst/" in str(n.get("tabelog", "")):
                err(f"{fp}: tabelog must be the restaurant's own page; list pages go in tabelog_list")
            if not n.get("tabelog") and not n.get("tabelog_list"):
                err(f"{fp}: restaurant needs tabelog or tabelog_list")
        if "closed" in n:
            check_closed(n["closed"], fp, err)
        p = n.get("place")
        if p is not None:
            if p not in paths:
                err(f"{fp}: place {p} does not resolve")
            elif nodes[paths[p]].get("type") != "city":
                err(f"{fp}: place {p} is not a city")
        if n.get("area") is not None:
            a = nodes.get(n["area"])
            if not a or a.get("type") != "area":
                err(f"{fp}: area {n['area']} is not an area node")
            elif a.get("place") != n.get("place"):
                err(f"{fp}: area {n['area']} belongs to {a.get('place')}, not {n.get('place')}")
        for k in ("country", "region", "capital"):
            if n.get(k) is not None and n[k] not in nodes:
                err(f"{fp}: {k} {n[k]} does not resolve")
        if t in ("region", "city"):
            want = f"{n.get('country')}/{n.get('region')}/{nid}" if t == "city" else f"{n.get('country')}/{nid}"
            if n.get("path") != want:
                err(f"{fp}: path {n.get('path')} should be {want} (country/region/id)")
        for x in n.get("near") or []:
            if x not in nodes:
                err(f"{fp}: near -> unknown id {x}")
        if t == "route":
            for k in ("origin", "destination"):
                if n.get(k) not in paths:
                    err(f"{fp}: route {k} {n.get(k)} does not resolve to a city path")
        if t == "event":
            eds = n.get("editions")
            if not isinstance(eds, list) or not eds:
                err(f"{fp}: event needs a non-empty editions list")
            else:
                for ed in eds:
                    if not isinstance(ed, dict) or not _is_date(ed.get("start")) or not _is_date(ed.get("end")):
                        err(f"{fp}: edition {ed} needs start/end dates")
                    elif d(ed["start"]) > d(ed["end"]):
                        err(f"{fp}: edition starts after it ends")
                    else:
                        for k in ("presale", "on_sale"):
                            if ed.get(k) is not None and not _is_date(ed[k]):
                                err(f"{fp}: edition {k} is not a date/datetime")
        if t == "country":
            for h in n.get("holidays") or []:
                if not _is_date(h):
                    err(f"{fp}: holiday {h} is not a date")
        if t == "trip":
            check_trip(n, nodes, paths, fp, err)
        if t == "day":
            if n.get("trip") not in nodes:
                err(f"{fp}: day trip {n.get('trip')} unknown")
                continue
            trip = nodes[n["trip"]]
            hol = hol_cache.setdefault(trip.get("country"), holidays(nodes, trip.get("country")))
            check_day(n, trip, nodes, paths, fp, err, warn, hol)

    check_links(root, err)

    # summary warnings (one line each, not per node)
    leaves = [n for n in nodes.values() if n.get("type") in ("activity", "hotel", "area", "restaurant")]
    nocoords = [n["id"] for n in leaves if not n.get("coords")]
    if nocoords:
        warn(f"{len(nocoords)} places without coords (run scripts/geocode.py): " + ", ".join(nocoords[:8])
             + (" ..." if len(nocoords) > 8 else ""))
    nodirect = sum(1 for n in nodes.values() if n.get("type") == "restaurant" and not n.get("tabelog"))
    if nodirect:
        warn(f"{nodirect} restaurants link only a Tabelog list page (add `tabelog:` with the restaurant's own page)")
    stats = summary(nodes, edges)
    return errors, warnings, stats


def check_trip(n, nodes, paths, fp, err):
    try:
        ts, te = trip_window(n)
    except (KeyError, ValueError, TypeError):
        err(f"{fp}: trip start/end must be dates")
        return
    if ts > te:
        err(f"{fp}: start after end")
    stops = n.get("stops") or []
    if not stops:
        err(f"{fp}: trip has no stops")
        return
    for i, s in enumerate(stops):
        if not (_is_date(s.get("from")) and _is_date(s.get("to"))):
            err(f"{fp}: stop {i + 1} from/to must be dates")
            return
        if d(s["from"]) >= d(s["to"]):
            err(f"{fp}: stop {s.get('place')} must have at least one night (from < to; `to` is the check-out day)")
        if s.get("place") not in paths:
            err(f"{fp}: stop place {s.get('place')} unknown")
        acc = s.get("accommodation")
        if acc:
            h = nodes.get(acc)
            if not h or h.get("type") != "hotel":
                err(f"{fp}: stop accommodation {acc} is not a hotel")
            elif h.get("place") != s.get("place"):
                err(f"{fp}: accommodation {acc} is in {h.get('place')}, not {s.get('place')}")
        if i and d(stops[i - 1]["to"]) != d(s["from"]):
            gap = "gap" if d(stops[i - 1]["to"]) < d(s["from"]) else "overlap"
            err(f"{fp}: stops must chain: {stops[i - 1]['place']} checks out {stops[i - 1]['to']} but "
                f"{s.get('place')} checks in {s['from']} ({gap} — a night without/with two hotels)")
    if d(stops[0]["from"]) != ts:
        err(f"{fp}: first stop must start on the trip start {ts}")
    if d(stops[-1]["to"]) != te:
        err(f"{fp}: last stop must end (check-out) on the trip end {te}")
    want = trip_day_ids(n)
    if (n.get("days") or []) != want:
        err(f"{fp}: days list is out of date — run scripts/sync.py")
    for x in want:
        if x not in nodes:
            err(f"{fp}: missing day node {x} — run scripts/sync.py")


def check_day(n, trip, nodes, paths, fp, err, warn, hol):
    if not _is_date(n.get("date")):
        err(f"{fp}: date must be YYYY-MM-DD")
        return
    day = d(n["date"])
    ts, te = trip_window(trip)
    if not ts <= day <= te:
        err(f"{fp}: date {day} outside trip {trip['id']}")
        return
    if n["id"] != day_id(trip["id"], day):
        err(f"{fp}: id should be {day_id(trip['id'], day)}")
    place, stay = expected_day(trip, day)
    if n.get("place") != place:
        err(f"{fp}: place {n.get('place')} should be {place} (city where we sleep that night)")
    if n.get("stay") != stay:
        err(f"{fp}: stay {n.get('stay')} should be {stay} (accommodation of the stop covering that night)")
    for v in n.get("visits") or []:
        if v not in paths:
            err(f"{fp}: visits {v} does not resolve")
    allowed = allowed_places(trip, n)
    vocab = SCHEMA["vocabularies"]["slot"]
    for it in plan_items(n):
        x = nodes.get(it["id"])
        if not x:
            err(f"{fp}: plan id {it['id']} unknown")
            continue
        if it.get("slot") is not None and it["slot"] not in vocab:
            err(f"{fp}: plan slot {it['slot']!r} not in {vocab}")
        if x.get("type") not in PLANNABLE:
            err(f"{fp}: plan id {it['id']} is a {x.get('type')} (allowed: {PLANNABLE})")
            continue
        if not node_places(x) & allowed:
            err(f"{fp}: {it['id']} is in {sorted(p for p in node_places(x) if p)}, not where we are on {day} "
                f"({sorted(allowed)}); add the city to `visits` for a day trip")
        if x["type"] == "event" and not edition_on(x, day):
            err(f"{fp}: event {it['id']} is not on {day} (editions: "
                + ", ".join(f"{e['start']}..{e['end']}" for e in editions(x)) + ")")
        for r in closures_on(x, day, hol):
            msg = f"{fp}: {it['id']} on {day} ({WEEKDAYS[day.weekday()]}): {describe_rule(r)}"
            if r.get("partial"):
                warn(msg + f" — partial: {r['partial']}")
            else:
                err(msg + " — move it to another day")
        if it.get("yen") is not None and (not isinstance(it["yen"], int) or it["yen"] < 0):
            err(f"{fp}: plan yen must be a non-negative integer")
    for x in n.get("done") or []:
        if not isinstance(x, dict) or x.get("id") not in nodes:
            err(f"{fp}: done item {x} must reference a node id")
        elif x.get("rating") is not None and x["rating"] not in (1, 2, 3, 4, 5):
            err(f"{fp}: done rating must be 1-5")
    for x in n.get("expenses") or []:
        if not isinstance(x, dict) or not isinstance(x.get("yen"), int) or x["yen"] < 0:
            err(f"{fp}: expense {x} needs a non-negative integer yen")
        elif x.get("category") is not None and x["category"] not in SCHEMA["vocabularies"]["expense_category"]:
            err(f"{fp}: expense category {x['category']!r} not in vocabulary")


def summary(nodes, edges):
    from collections import Counter
    counts = Counter(n.get("type") for n in nodes.values())
    per_city = {}
    strict = set(strict_restaurants(nodes))
    for nid, n in nodes.items():
        if n.get("type") == "restaurant":
            c = per_city.setdefault(n.get("place", "").split("/")[-1], [0, 0])
            c[0] += 1
            c[1] += nid in strict
    return [f"{len(nodes)} nodes: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())),
            f"{len(edges)} edges",
            "restaurants per city (total / strict >= 3.5 with a meal <= ¥4,999): "
            + ", ".join(f"{c}: {t}/{s}" for c, (t, s) in sorted(per_city.items()))]


def main(root=REPO):
    errors, warnings, stats = validate(root)
    for line in stats:
        print(line)
    if warnings:
        print(f"\n{len(warnings)} warnings:")
        for w in warnings:
            print(" ~", w)
    if errors:
        print(f"\n{len(errors)} ERRORS:")
        for e in errors:
            print(" -", e)
        return 1
    print("\nGraph consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else REPO))
