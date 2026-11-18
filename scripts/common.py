"""Shared logic for the travel graph scripts: loading, derived edges, trips/days, closures,
budgets and geography. Every function takes the data it needs, so tests can run on a temp repo."""
import math
import os
import re
from datetime import date, datetime, timedelta

import yaml

import fm as fmio

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST_TYPES = ("country", "region", "city", "area", "activity", "event", "restaurant", "hotel", "route")
CITY_LEAF_TYPES = ("area", "activity", "event", "restaurant", "hotel")
LEAF_FOLDERS = {"area": "areas", "activity": "activities", "event": "events", "restaurant": "restaurants",
                "hotel": "hotels"}
PLANNABLE = ("activity", "event", "restaurant", "route", "hotel")
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def load_schema(root=REPO):
    with open(os.path.join(root, "schema.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


SCHEMA = load_schema()
SLOT_ORDER = {s: i for i, s in enumerate(SCHEMA["vocabularies"]["slot"])}


def rel(fp, root=REPO):
    return os.path.relpath(fp, root)


# ---------------------------------------------------------------- dates

def d(s):
    """Parse a date/datetime/str into a date (first 10 chars)."""
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    return date.fromisoformat(str(s)[:10])


def daterange(a, b):
    """Dates a..b-1 (b exclusive)."""
    x = a
    while x < b:
        yield x
        x += timedelta(days=1)


# ---------------------------------------------------------------- loading

def iter_node_files(root=REPO):
    for base in ("destinations", "trips"):
        for dirpath, dirs, files in os.walk(os.path.join(root, base)):
            dirs.sort()
            for f in sorted(files):
                if f.endswith(".md"):
                    yield os.path.join(dirpath, f)


def read(fp):
    with open(fp, encoding="utf-8", newline="") as f:
        return f.read()


def write(fp, text):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def parse_node(fp):
    """Return (fm, body, error). fm is None for non-node files (no frontmatter)."""
    fm, body, err = fmio.parse(read(fp))
    if err:
        return None, body, err
    if fm is not None and "id" not in fm:
        return None, body, "frontmatter has no 'id'"
    return fm, body, None


def load_graph(root=REPO, errors=None):
    """Load every node. Parse errors and duplicate ids are appended to `errors` (when given)
    instead of being silently dropped. Returns (nodes, paths, edges)."""
    nodes, paths = {}, {}
    for fp in iter_node_files(root):
        fm, body, err = parse_node(fp)
        if err:
            if errors is not None:
                errors.append(f"{rel(fp, root)}: {err}")
            continue
        if fm is None:
            continue
        nid = str(fm["id"])
        if nid in nodes:
            if errors is not None:
                errors.append(f"duplicate id '{nid}': {rel(nodes[nid]['_fp'], root)} and {rel(fp, root)}")
            continue
        fm["id"] = nid
        fm["_fp"], fm["_body"] = fp, body
        nodes[nid] = fm
        p = fm.get("path")
        if p:
            if p in paths and errors is not None:
                errors.append(f"duplicate path '{p}': {paths[p]} and {nid}")
            paths.setdefault(p, nid)
    return nodes, paths, derive_edges(nodes, paths)


def public(n):
    return {k: v for k, v in n.items() if not k.startswith("_")}


def _empty(v):
    return v is None or v == "" or v == [] or v == {}


def _canon_map(m, required, keys):
    out = {}
    for k in list(keys) + sorted(k for k in m if k not in keys):
        if k in m and not (k not in required and _empty(m[k])):
            out[k] = m[k]
    return out


def canonical(n, schema=SCHEMA):
    """Frontmatter in schema key order, without empty optional keys or stripped geo lists.
    Unknown keys are kept (at the end) so the validator can report them."""
    t = n.get("type")
    spec = schema["types"].get(t)
    data = public(n)
    if not spec:
        return data
    if t in ("country", "region", "city"):
        data = {k: v for k, v in data.items() if k not in schema["geo_strip_keys"]}
    out = _canon_map(data, set(spec["required"]), spec["keys"])
    for k, nspec in schema["nested"].items():
        if isinstance(out.get(k), list):
            out[k] = [_canon_map(x, set(nspec["required"]), nspec["keys"]) if isinstance(x, dict) else x
                      for x in out[k]]
    return out


# ---------------------------------------------------------------- geography

def haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def sun_times(lat, lon, day, tz_hours=9.0):
    """(sunrise, sunset) as minutes after local midnight (NOAA general solar position, ±2 min)."""
    day = d(day)
    g = 2 * math.pi / 365 * (day.timetuple().tm_yday - 1)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    la = math.radians(lat)
    x = math.cos(math.radians(90.833)) / (math.cos(la) * math.cos(decl)) - math.tan(la) * math.tan(decl)
    ha = math.degrees(math.acos(max(-1.0, min(1.0, x))))
    rise = 720 - 4 * (lon + ha) - eqtime + tz_hours * 60
    sset = 720 - 4 * (lon - ha) - eqtime + tz_hours * 60
    return round(rise), round(sset)


def hhmm(minutes):
    return f"{int(minutes) // 60:02d}:{int(minutes) % 60:02d}"


HOURS_RE = re.compile(r"(\d{1,2}):(\d{2})\s*[-–]\s*(?:(\d{1,2}):(\d{2})|(sunset))", re.I)
# minutes after midnight in which each plan slot usually happens
SLOT_WINDOWS = {"early": (300, 510), "morning": (510, 720), "day": (540, 1020), "lunch": (660, 870),
                "afternoon": (780, 1020), "evening": (1020, 1200), "dinner": (1080, 1290), "night": (1200, 1440)}


def parse_hours(text, sunset=None):
    """Opening window (open, close) in minutes from free text like '9:00-17:00 (last entry 16:30)',
    '5:00-sunset' or 'Nov–Mar ~9:00-16:00'. Returns 'always' for 24h places, None when unknown."""
    if not text:
        return None
    m = HOURS_RE.search(str(text))
    if "24h" in str(text).lower().replace(" ", "") and not m:
        return "always"
    if not m:
        return "always" if "24h" in str(text).lower() else None
    if "24h" in str(text).lower():
        return "always"  # e.g. "park 24h; museum 9:30-17:00": the place itself can be visited
    op = int(m.group(1)) * 60 + int(m.group(2))
    if m.group(5):
        if sunset is None:
            return None
        cl = sunset
    else:
        cl = int(m.group(3)) * 60 + int(m.group(4))
    if cl <= op:
        cl += 24 * 60
    return op, cl


def _hm(s):
    h, m = str(s).split(":")
    return int(h) * 60 + int(m)


def opening_windows(n, day, hol=frozenset()):
    """Opening windows (minutes) on a date from structured `opening`, or None when unknown.
    A public holiday uses the `hol` entry when present, otherwise the weekday; [] = not open."""
    rows = n.get("opening")
    if not isinstance(rows, list) or not rows:
        return None
    day = d(day)
    keys = [WEEKDAYS[day.weekday()]]
    if day in hol:
        keys.insert(0, "hol")
    elif day + timedelta(days=1) in hol:
        keys.insert(0, "pre_hol")
    elif day - timedelta(days=1) in hol:
        keys.insert(0, "post_hol")
    for k in keys:
        for r in rows:
            if k in (r.get("days") or []):
                out = []
                for t in r.get("times") or []:
                    a, b = str(t).split("-")
                    op, cl = _hm(a), _hm(b)
                    out.append((op, cl + 1440 if cl <= op else cl))
                return out
    return []


def coords(n):
    c = n.get("coords")
    if isinstance(c, (list, tuple)) and len(c) == 2:
        return float(c[0]), float(c[1])
    return None


def city_id_of(n, paths):
    """City id a node belongs to (place for leaves, itself for cities)."""
    if n.get("type") == "city":
        return n["id"]
    return paths.get(n.get("place"))


def city_children(nodes, city_path, types=CITY_LEAF_TYPES):
    """Destination nodes located in a city. Trip/day nodes are excluded on purpose."""
    return sorted(nid for nid, n in nodes.items() if n.get("place") == city_path and n.get("type") in types)


def ancestors(nodes, cid):
    """[region, country] of a city (no duplicates)."""
    out = []
    c = nodes[cid]
    for k in ("region", "country"):
        if c.get(k) in nodes and c[k] not in out:
            out.append(c[k])
    return out


def expected_file(n, nodes, paths, root=REPO):
    """Where a node must live, derived from its own fields (None when it cannot be derived)."""
    t, nid = n.get("type"), n["id"]
    if t == "country":
        return os.path.join(root, "destinations", nid, "README.md")
    if t == "region":
        return os.path.join(root, "destinations", str(n.get("country")), "regions", nid, "README.md")
    if t == "city":
        return os.path.join(root, "destinations", str(n.get("country")), "regions", str(n.get("region")),
                            "cities", nid, "README.md")
    if t in LEAF_FOLDERS:
        city = paths.get(n.get("place"))
        if not city or city not in nodes:
            return None
        return os.path.join(os.path.dirname(expected_file(nodes[city], nodes, paths, root)),
                            LEAF_FOLDERS[t], nid + ".md")
    if t == "route":
        country = str(n.get("origin", "")).split("/")[0]
        return os.path.join(root, "destinations", country, "routes", nid + ".md")
    if t == "trip":
        return os.path.join(root, "trips", nid, "README.md")
    if t == "day":
        trip = nodes.get(n.get("trip"))
        if not trip:
            return None
        return os.path.join(os.path.dirname(trip["_fp"]), "days", str(n.get("date")) + ".md")
    return None


# ---------------------------------------------------------------- trips and days

def day_id(trip_id, day):
    return f"{trip_id}-{d(day).isoformat()}"


def trip_window(trip):
    return d(trip["start"]), d(trip["end"])


def trip_nights(trip):
    """{date: stop} for every night of the trip. A stop covers nights from..to-1 (`to` = check-out)."""
    out = {}
    for s in trip.get("stops") or []:
        for x in daterange(d(s["from"]), d(s["to"])):
            out[x] = s
    return out


def expected_day(trip, day):
    """(place, stay) a day node must have: the city where we sleep that night; the last day
    (departure) keeps the last stop's city and has no stay."""
    nights = trip_nights(trip)
    day = d(day)
    if day in nights:
        s = nights[day]
        return s.get("place"), s.get("accommodation")
    stops = trip.get("stops") or []
    if stops and day == d(trip["end"]):
        return stops[-1].get("place"), None
    return None, None


def trip_day_ids(trip):
    a, b = trip_window(trip)
    return [day_id(trip["id"], x) for x in daterange(a, b + timedelta(days=1))]


def allowed_places(trip, day):
    """Cities a day's plan may reference: where we sleep, where we slept the night before
    (travel days) and any day-trip `visits`."""
    out = {day.get("place")}
    prev = trip_nights(trip).get(d(day["date"]) - timedelta(days=1))
    if prev:
        out.add(prev.get("place"))
    out.update(day.get("visits") or [])
    out.discard(None)
    return out


def node_places(n):
    if n.get("type") == "route":
        return {n.get("origin"), n.get("destination")}
    return {n.get("place")}


def plan_items(day):
    """Normalize `plan` entries ({slot, id, note} mappings or bare ids) and sort them by slot."""
    out = []
    for i, item in enumerate(day.get("plan") or []):
        if isinstance(item, str):
            item = {"id": item}
        if isinstance(item, dict) and item.get("id"):
            out.append(dict(item, _i=i))
    out.sort(key=lambda x: (SLOT_ORDER.get(x.get("slot"), SLOT_ORDER["day"]), x["_i"]))
    for x in out:
        x.pop("_i")
    return out


# ---------------------------------------------------------------- events

def editions(e):
    out = []
    for ed in e.get("editions") or []:
        try:
            out.append(dict(ed, start=d(ed["start"]), end=d(ed["end"])))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def edition_on(e, day):
    day = d(day)
    return next((ed for ed in editions(e) if ed["start"] <= day <= ed["end"]), None)


def editions_overlapping(e, a, b):
    return [ed for ed in editions(e) if ed["start"] <= b and ed["end"] >= a]


def events_on(nodes, places, day):
    return sorted(nid for nid, n in nodes.items()
                  if n.get("type") == "event" and n.get("place") in places and edition_on(n, day))


# ---------------------------------------------------------------- closures

def holidays(nodes, country_id):
    c = nodes.get(country_id) or {}
    out = set()
    for h in c.get("holidays") or []:
        try:
            out.add(d(h))
        except ValueError:
            pass
    return out


def _md(s):
    m, dd = str(s).split("-")
    return int(m), int(dd)


def _nth_ok(rule, day):
    nth = rule.get("nth")
    return not nth or ((day.day - 1) // 7 + 1) in nth


def _weekly_hit(rule, day, hol):
    days = rule.get("weekly") or []
    shift = rule.get("holiday_shift")
    if WEEKDAYS[day.weekday()] in days and _nth_ok(rule, day):
        if not (shift and day in hol):
            return True
    if shift:  # closed day moved to the next day when it falls on a public holiday
        prev = day - timedelta(days=1)
        if prev in hol and WEEKDAYS[prev.weekday()] in days and _nth_ok(rule, prev):
            return True
    return False


def rule_matches(rule, day, hol=frozenset()):
    day = d(day)
    if "weekly" in rule:
        return _weekly_hit(rule, day, hol)
    if "yearly" in rule:
        a, b = (_md(x) for x in str(rule["yearly"]).split(".."))
        md = (day.month, day.day)
        return a <= md <= b if a <= b else (md >= a or md <= b)
    if "dates" in rule:
        a, b = (d(x) for x in str(rule["dates"]).split(".."))
        return a <= day <= b
    if "specific" in rule:
        return day in {d(x) for x in rule["specific"]}
    if rule.get("holidays"):
        return day in hol
    return False  # `irregular` notes never match a date


def soft_closure(r):
    """Text when a closure rule only warns (part of the place, or a possible closure), else None."""
    if r.get("partial"):
        return r["partial"]
    if r.get("maybe"):
        return f"may be closed: {r['maybe']}"
    return None


def closures_on(n, day, hol=frozenset()):
    """Closure rules of a node that apply on `day` (each rule may carry `partial`)."""
    rules = n.get("closed")
    if not isinstance(rules, list):
        return []
    return [r for r in rules if isinstance(r, dict) and rule_matches(r, day, hol)]


def describe_rule(r):
    if "weekly" in r:
        s = "/".join(r["weekly"])
        if r.get("nth"):
            s = "/".join(map(str, r["nth"])) + " " + s + " of the month"
        return f"closed {s}" + (" (holiday → next day)" if r.get("holiday_shift") else "")
    if "yearly" in r:
        return f"closed {r['yearly']} every year"
    if "dates" in r:
        return f"closed {r['dates']}"
    if "specific" in r:
        return "closed on " + ", ".join(map(str, r["specific"]))
    if r.get("holidays"):
        return "closed on public holidays"
    return str(r.get("irregular", ""))


# ---------------------------------------------------------------- money

def price_range_yen(pr, schema=SCHEMA):
    r = schema["price_range_yen"].get(pr)
    return tuple(r) if r else None


def bucket_for_yen(yen, schema=SCHEMA):
    for k, (lo, hi) in schema["price_range_yen"].items():
        if yen >= lo and (hi is None or yen <= hi):
            return k
    return None


def derive_fields(n, schema=SCHEMA):
    """Fields that must follow from others (applied by sync before writing):
    restaurant price_range from its budgets and the `top-rated` tag from tabelog_rating."""
    if n.get("type") != "restaurant":
        return n
    r = next((n[k] for k in ("budget_dinner_yen", "budget_yen", "budget_lunch_yen")
              if isinstance(n.get(k), list) and len(n[k]) == 2), None)
    if r:
        yen = r[0] if r[0] is not None else r[1]
        if yen is not None:
            n["price_range"] = bucket_for_yen(yen, schema) or n.get("price_range")
    tags = [t for t in (n.get("tags") or []) if t != "top-rated"]
    if n.get("tabelog_rating") is not None and float(n["tabelog_rating"]) >= schema["strict_restaurants"]["min_rating"]:
        tags.append("top-rated")
    n["tags"] = tags
    return n


def _mid(r):
    lo, hi = r
    if lo is None and hi is None:
        return None
    if lo is None:
        return hi
    if hi is None:
        return lo
    return round((lo + hi) / 2)


def restaurant_range(n, slot=None, schema=SCHEMA):
    """(lo, hi) yen per person for a meal; slot picks lunch/dinner budget when known."""
    order = {"lunch": ["budget_lunch_yen", "budget_yen", "budget_dinner_yen"],
             "dinner": ["budget_dinner_yen", "budget_yen", "budget_lunch_yen"]}.get(
        slot, ["budget_yen", "budget_lunch_yen", "budget_dinner_yen"])
    for k in order:
        if isinstance(n.get(k), list) and len(n[k]) == 2:
            return tuple(n[k])
    return price_range_yen(n.get("price_range"), schema)


def cheapest_meal_yen(n, schema=SCHEMA):
    """Upper bound of the cheapest known meal (used by the strict < ¥5,000 filter)."""
    his = [n[k][1] for k in ("budget_lunch_yen", "budget_dinner_yen", "budget_yen")
           if isinstance(n.get(k), list) and len(n[k]) == 2 and n[k][1] is not None]
    if his:
        return min(his)
    r = price_range_yen(n.get("price_range"), schema)
    return r[1] if r else None


def estimate_yen(n, slot=None, schema=SCHEMA):
    """Estimated cost per person of doing a node, or None when unknown."""
    t = n.get("type")
    if t == "restaurant":
        r = restaurant_range(n, slot, schema)
        return _mid(r) if r else None
    if t == "route":
        return n.get("price_yen")
    if t in ("activity", "event"):
        if n.get("cost_yen") is not None:
            return n["cost_yen"]
        if n.get("entry") == "free":
            return 0
        return None
    return None


def strict_restaurants(nodes, schema=SCHEMA):
    rule = schema["strict_restaurants"]
    out = []
    for nid, n in sorted(nodes.items()):
        if n.get("type") != "restaurant" or n.get("tabelog_rating") is None:
            continue
        cheap = cheapest_meal_yen(n, schema)
        if float(n["tabelog_rating"]) >= rule["min_rating"] and cheap is not None and cheap <= rule["max_yen"]:
            out.append(nid)
    return out


# ---------------------------------------------------------------- edges

def derive_edges(nodes, paths, schema=SCHEMA):
    edges = []

    def add(a, b, rel, **meta):
        if a in nodes and b in nodes and a != b:
            e = {"from": a, "to": b, "rel": rel}
            e.update(meta)
            edges.append(e)

    for nid, n in nodes.items():
        t = n.get("type")
        if n.get("place") in paths:
            add(nid, paths[n["place"]], "place")
        if t in ("region", "city"):
            add(nid, n.get("country"), "country")
        if t == "city":
            add(nid, n.get("region"), "region")
        p = n.get("path")
        if p and "/" in p and p.rsplit("/", 1)[0] in paths:
            add(nid, paths[p.rsplit("/", 1)[0]], "parent")
        if n.get("area"):
            add(nid, n["area"], "area")
        for x in n.get("near") or []:
            add(nid, x, "near")
        if t == "route":
            add(nid, paths.get(n.get("origin")), "origin")
            add(nid, paths.get(n.get("destination")), "destination")
        if t == "trip":
            a, b = trip_window(n)
            places = set()
            for s in n.get("stops") or []:
                places.add(s.get("place"))
                add(nid, paths.get(s.get("place")), "stop", check_in=str(s.get("from")), check_out=str(s.get("to")))
                if s.get("accommodation"):
                    add(nid, s["accommodation"], "stay")
            for eid, e in nodes.items():
                if e.get("type") == "event" and e.get("place") in places and editions_overlapping(e, a, b):
                    add(nid, eid, "event")
            for x in n.get("days") or []:
                add(nid, x, "day")
        if t == "day":
            add(nid, n.get("trip"), "trip")
            add(nid, paths.get(n.get("place")), "place")
            if n.get("stay"):
                add(nid, n["stay"], "stay")
            for v in n.get("visits") or []:
                add(nid, paths.get(v), "visit")
            for item in plan_items(n):
                meta = {"slot": item["slot"]} if item.get("slot") else {}
                add(nid, item["id"], "plan", **meta)
            trip = nodes.get(n.get("trip"))
            if trip:
                for eid in events_on(nodes, allowed_places(trip, n), n["date"]):
                    add(nid, eid, "event")
            for x in n.get("done") or []:
                if isinstance(x, dict):
                    meta = {"rating": x["rating"]} if x.get("rating") is not None else {}
                    add(nid, x.get("id"), "done", **meta)
                    if n.get("trip") in nodes:
                        add(x.get("id"), n["trip"], "done_in")
    edges.extend(proximity_edges(nodes, paths, schema))
    uniq = {}
    for e in edges:
        uniq[(e["from"], e["rel"], e["to"])] = e
    return [uniq[k] for k in sorted(uniq)]


def proximity_edges(nodes, paths, schema=SCHEMA):
    """Derived `nearby` (sight/hotel/area -> closest restaurants and sights) and `in_area` edges."""
    cfg, area_km = schema["nearby"], schema["in_area_km"]
    by_city = {}
    for nid, n in nodes.items():
        if n.get("type") in CITY_LEAF_TYPES and coords(n):
            by_city.setdefault(n.get("place"), []).append(nid)
    out = []
    for place, ids in sorted(by_city.items()):
        typed = {t: [i for i in ids if nodes[i]["type"] == t] for t in ("activity", "restaurant", "area", "event")}
        for src in ids:
            s = nodes[src]
            if s["type"] == "restaurant":
                continue
            for t in ("activity", "restaurant"):
                cands = []
                for dst in typed[t]:
                    if dst == src:
                        continue
                    km = haversine_km(coords(s), coords(nodes[dst]))
                    if km <= cfg["km"]:
                        cands.append((round(km, 2), dst))
                for km, dst in sorted(cands)[:cfg["per_type"]]:
                    out.append({"from": src, "to": dst, "rel": "nearby", "km": km})
        for src in ids:
            s = nodes[src]
            if s["type"] in ("area", "restaurant", "hotel") or s.get("area"):
                continue
            best = min(((haversine_km(coords(s), coords(nodes[a])), a) for a in typed["area"]), default=None)
            if best and best[0] <= area_km:
                out.append({"from": src, "to": best[1], "rel": "in_area", "km": round(best[0], 2)})
    return out


def area_of(nid, nodes, edges):
    n = nodes[nid]
    if n.get("area"):
        return n["area"]
    return next((e["to"] for e in edges if e["from"] == nid and e["rel"] == "in_area"), None)
