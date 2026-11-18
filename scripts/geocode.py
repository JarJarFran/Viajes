"""Fill `coords` (plus `name_ja` / `address_ja` when OSM has them) from OpenStreetMap Nominatim.

    python3 scripts/geocode.py                 # every node without coords
    python3 scripts/geocode.py --ids a,b       # only these ids (re-geocode even if they have coords)
    python3 scripts/geocode.py --query kyoto-area-gion="Gion, Kyoto"   # override the search text
    python3 scripts/geocode.py --dry-run       # print what would change

Precision: `exact` (the place itself was found), `station` (restaurants: nearest station from
`station`), `area` (fallback to the area centroid). Results are checked against the city centre
and cached in scripts/.geocache.json. Nominatim policy: max 1 request/second, identify the client.
Data © OpenStreetMap contributors, ODbL.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm as fmio  # noqa: E402
from common import REPO, canonical, coords, haversine_km, load_graph, write  # noqa: E402

API = "https://nominatim.openstreetmap.org/search"
UA = "travel-graph-geocoder/1.0"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".geocache.json")
JA = re.compile(r"[぀-ヿ㐀-鿿]")
RADIUS_KM = {"area": 25, "restaurant": 25, "hotel": 25, "activity": 40, "event": 40}
_last = [0.0]


def search(q, cache, viewbox=None, details=False):
    key = ("nd|" if details else "") + q + (f"|{viewbox}" if viewbox else "")
    if key in cache:
        return cache[key]
    params = {"q": q, "format": "jsonv2", "limit": 5, "countrycodes": "jp", "accept-language": "ja",
              "addressdetails": 1}
    if details:
        params["namedetails"] = 1
    if viewbox:
        params.update(viewbox=viewbox, bounded=1)
    wait = 1.1 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.load(r)
            break
        except Exception as e:  # network hiccup: back off and retry
            if attempt == 3:
                print(f"  ! {q}: {e}", file=sys.stderr)
                return []
            time.sleep(2 ** attempt * 2)
    _last[0] = time.time()
    cache[key] = [{"lat": float(x["lat"]), "lon": float(x["lon"]), "name": x.get("name") or "",
                   "class": x.get("category") or x.get("class"), "kind": x.get("type"),
                   "display": x.get("display_name", ""), "rank": x.get("place_rank"),
                   "names": {k: v for k, v in (x.get("namedetails") or {}).items()
                             if k == "name" or k.startswith("name:en") or k.startswith("name:ja") or k.startswith("brand")}}
                  for x in res]
    return cache[key]


GENERIC = set("""restaurant ramen honten ten shop store branch main the no soba udon sushi curry cafe coffee izakaya
tonkatsu yakitori okonomiyaki takoyaki gyoza menya men ya tei an kyoto osaka tokyo shinjuku shibuya ginza namba umeda
gion station eki dining kitchen bar house japan""".split())


def _tokens(s):
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in GENERIC and len(t) > 1}


def name_matches(ours, hit):
    """True when one of the hit's Latin-script names shares most significant words with ours."""
    mine = _tokens(clean_name(ours))
    compact = re.sub(r"[^a-z0-9]", "", clean_name(ours).lower())
    for v in (hit.get("names") or {}).values():
        if JA.search(v) and not re.search(r"[a-z]{3}", v.lower()):
            continue
        theirs = _tokens(v)
        other = re.sub(r"[^a-z0-9]", "", v.lower())
        if mine and theirs and len(mine & theirs) / min(len(mine), len(theirs)) >= 0.6:
            return True
        if len(compact) >= 5 and (compact in other or (len(other) >= 5 and other in compact)):
            return True
    return False


def clean_name(name):
    s = re.sub(r"\(.*?\)", "", name)
    s = re.sub(r"^(Day trip( to)?|Day trip Osaka →|Day trip Kyoto →)\s*", "", s, flags=re.I)
    s = re.sub(r"\s+(at night|at dusk)$", "", s, flags=re.I)
    s = s.split(" & ")[0].split(" and ")[0]
    return s.strip(" -—")


def address_ja(hit):
    parts = [p.strip() for p in hit["display"].split(",")]
    parts = [p for p in parts if p and p != hit["name"] and p != "日本"]
    post = next((p for p in parts if re.match(r"^\d{3}-\d{4}$", p)), None)
    parts = [p for p in parts if p != post]
    s = "".join(reversed(parts))
    return (f"〒{post} " if post else "") + s if s else None


def pick(hits, center, radius, skip_boundary=True):
    good = []
    for h in hits:
        if skip_boundary and h["class"] == "boundary" and h["kind"] == "administrative":
            continue
        km = haversine_km(center, (h["lat"], h["lon"])) if center and radius else 0
        if not radius or km <= radius:
            good.append(h)
    return good[0] if good else None


def box(c, km):
    dlat = km / 111.0
    dlon = km / (111.0 * max(0.2, abs(__import__("math").cos(__import__("math").radians(c[0])))))
    return f"{c[1] - dlon},{c[0] + dlat},{c[1] + dlon},{c[0] - dlat}"


def geocode_node(n, nodes, paths, cache, override=None):
    t = n["type"]
    city = nodes.get(paths.get(n.get("place"))) if t != "city" else n
    cname = city["name"] if city else ""
    center = coords(city) if city and t != "city" else None
    radius = RADIUS_KM.get(t, 30)
    if override:
        hit = pick(search(override, cache), center, radius if t not in ("activity", "area") else 0,
                   skip_boundary=t != "city")
        return (hit, "exact") if hit else (None, None)
    if t == "city":
        hit = pick(search(f"{n['name']}, {n.get('prefecture') or ''}".strip(", "), cache), None, 0, skip_boundary=False)
        return (hit, "exact") if hit else (None, None)
    if t == "restaurant":
        st = None
        if n.get("station"):
            st = pick(search(f"{n['station']}駅, {cname}" if JA.search(n["station"]) else f"{n['station']} Station, {cname}",
                             cache), center, radius)
        anchor = (st["lat"], st["lon"]) if st else coords(nodes.get(n.get("area"), {}))
        if anchor:
            r_km = max(0.6, (n.get("station_m") or 500) / 1000 + 0.6)
            hits = search(clean_name(n["name"]), cache, box(anchor, r_km), details=True)
            hit = next((h for h in hits if h["class"] in ("amenity", "shop", "tourism", "building")
                        and name_matches(n["name"], h)), None)
            if hit:
                return hit, "exact"
        if st:
            return dict(st, name="", display=""), "station"
        area = nodes.get(n.get("area"))
        if area and coords(area):
            c = coords(area)
            return {"lat": c[0], "lon": c[1], "name": "", "display": ""}, "area"
        return None, None
    queries = [f"{clean_name(n['name'])}, {cname}", clean_name(n["name"])]
    inner = re.findall(r"\((.*?)\)", n["name"])
    queries += [f"{x}, {cname}" for x in inner]
    for q in queries:
        hit = pick(search(q, cache), center, radius)
        if hit:
            return hit, "exact"
    return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", help="comma-separated ids (re-geocode even when coords exist)")
    ap.add_argument("--types", default="city,area,activity,event,hotel,restaurant")
    ap.add_argument("--query", action="append", default=[], help="id=search text override (repeatable)")
    ap.add_argument("--overrides", help="JSON file {id: search text}")
    ap.add_argument("--force", action="store_true", help="re-geocode nodes that already have coords")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    overrides = dict(x.split("=", 1) for x in a.query)
    if a.overrides:
        overrides.update(json.load(open(a.overrides, encoding="utf-8")))
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    nodes, paths, _ = load_graph(REPO)
    want = set(a.ids.split(",")) if a.ids else None
    order = {t: i for i, t in enumerate(a.types.split(","))}
    todo = [n for n in nodes.values() if n.get("type") in order
            and (n["id"] in want if want else (a.force or not n.get("coords")))]
    todo.sort(key=lambda n: (order[n["type"]], n["id"]))
    stats = {"exact": 0, "station": 0, "area": 0, "miss": 0}
    misses = []
    try:
        for i, n in enumerate(todo, 1):
            hit, prec = geocode_node(n, nodes, paths, cache, overrides.get(n["id"]))
            if not hit:
                stats["miss"] += 1
                misses.append(n["id"])
                continue
            stats[prec] += 1
            n["coords"] = [round(hit["lat"], 6), round(hit["lon"], 6)]
            if n["type"] not in ("city", "region"):
                n["coords_precision"] = prec
            # only fill missing Japanese names/addresses: curated or Tabelog values are never overwritten
            # (an event's venue name is not the event's name, so events are skipped)
            if prec == "exact" and n["type"] not in ("area", "city", "event") and JA.search(hit.get("name", "")):
                n.setdefault("name_ja", hit["name"])
                adr = address_ja(hit)
                if adr and n["type"] != "restaurant":
                    n.setdefault("address_ja", adr)
            print(f"[{i}/{len(todo)}] {n['id']}: {prec} {n['coords']} {n.get('name_ja', '')}")
            if not a.dry_run:
                write(n["_fp"], fmio.render(canonical(n), n["_body"]))
    finally:
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=0, sort_keys=True)
    print(stats)
    if misses:
        print("not found (use --query id=\"text\"):", ", ".join(misses))


if __name__ == "__main__":
    main()
