import re, sys
from datetime import date
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import REPO, SCHEMA, load_graph, public, d

errors = []
nodes, paths, edges = load_graph()

by_id = {}
for nid, n in nodes.items():
    if nid in by_id:
        errors.append(f"duplicate id {nid} ({by_id[nid]['_fp']} and {n['_fp']})")
    by_id[nid] = n

id_re = re.compile(SCHEMA["id_pattern"])
vocab = SCHEMA["vocabularies"]
date_fields = set(SCHEMA["date_fields"])

for nid, n in sorted(nodes.items()):
    fp = n["_fp"]
    t = n.get("type")
    if not id_re.match(nid):
        errors.append(f"{fp}: id '{nid}' does not match {SCHEMA['id_pattern']}")
    if t not in SCHEMA["types"]:
        errors.append(f"{fp}: unknown type {t}")
        continue
    for req in SCHEMA["types"][t]["required"]:
        if req not in n:
            errors.append(f"{fp}: {t} missing required key '{req}'")
    for f in date_fields:
        if f in n and n[f] is not None:
            try:
                d(n[f])
            except ValueError:
                errors.append(f"{fp}: '{f}' is not YYYY-MM-DD: {n[f]}")
    for f in ("start", "end"):
        if t in ("event", "trip") and f in n:
            try:
                d(n[f])
            except ValueError:
                errors.append(f"{fp}: bad {f}")
    for enum_key in ("entry", "booking", "price_range", "status"):
        if enum_key in n and n[enum_key] is not None and n[enum_key] not in vocab[enum_key]:
            errors.append(f"{fp}: {enum_key}={n[enum_key]!r} not in {vocab[enum_key]}")
    for tag in n.get("tags") or []:
        if tag not in vocab["tags"]:
            errors.append(f"{fp}: tag {tag!r} not in vocabulary")
    r = n.get("tabelog_rating")
    if r is not None and not (0 <= float(r) <= 5):
        errors.append(f"{fp}: tabelog_rating {r} out of range")
    p = n.get("place")
    if p is not None:
        if p not in paths:
            errors.append(f"{fp}: place {p} does not resolve")
        elif nodes[paths[p]].get("type") != "city":
            errors.append(f"{fp}: place {p} is not a city node")
    for k in ("country", "region"):
        if k in n and n[k] is not None and n[k] not in nodes and n[k] not in paths:
            errors.append(f"{fp}: {k} {n[k]} does not resolve")
    for k in ("near", "done_in"):
        for v in n.get(k) or []:
            if v not in nodes:
                errors.append(f"{fp}: {k} -> unknown id {v}")
    if t == "trip":
        try:
            ts, te = d(n["start"]), d(n["end"])
        except Exception:
            ts = te = None
        if ts and te and ts > te:
            errors.append(f"{fp}: start after end")
        for s in n.get("stops", []):
            sp = s.get("place")
            if sp not in paths:
                errors.append(f"{fp}: stop place {sp} unknown")
            else:
                if ts and te:
                    try:
                        sf, st = d(s["from"]), d(s["to"])
                        if sf < ts or st > te or sf > st:
                            errors.append(f"{fp}: stop {sp} {sf}..{st} outside trip window or inverted")
                    except ValueError:
                        errors.append(f"{fp}: stop dates invalid")
            if s.get("accommodation") and s["accommodation"] not in nodes:
                errors.append(f"{fp}: stop accommodation {s['accommodation']} unknown")
            for a in s.get("activities") or []:
                if a not in nodes:
                    errors.append(f"{fp}: stop activity {a} unknown")
            for dk in ("from", "to"):
                if dk in s:
                    try:
                        d(s[dk])
                    except ValueError:
                        errors.append(f"{fp}: stop {dk} not a date")
        for ev in n.get("events") or []:
            if ev not in nodes:
                errors.append(f"{fp}: trip event {ev} unknown")
            elif ts and te:
                e = nodes[ev]
                if d(e["end"]) < ts or d(e["start"]) > te:
                    errors.append(f"{fp}: event {ev} does not overlap trip window")
        for dayid in n.get("days") or []:
            if dayid not in nodes:
                errors.append(f"{fp}: day {dayid} unknown")
            elif ts and te:
                dn = nodes[dayid]
                if not (ts <= d(dn["date"]) <= te):
                    errors.append(f"{fp}: day {dayid} outside trip window")
                stop = next((s for s in n.get("stops", []) if s.get("place") == dn.get("place") and d(s["from"]) <= d(dn["date"]) <= d(s["to"])), None)
                if stop is None:
                    errors.append(f"{fp}: day {dayid} place/date not covered by any stop")
    if t == "day":
        if n.get("trip") not in nodes:
            errors.append(f"{fp}: day trip {n.get('trip')} unknown")
        allowed = {s.get("place") for s in nodes[n["trip"]].get("stops", [])} if n.get("trip") in nodes else {n.get("place")}
        for a in n.get("plan") or []:
            if a not in nodes:
                errors.append(f"{fp}: plan id {a} unknown")
            elif nodes[a].get("place") not in allowed:
                errors.append(f"{fp}: plan id {a} is not in a stop of trip {n.get('trip')}")
        for ev in n.get("events") or []:
            if ev not in nodes:
                errors.append(f"{fp}: day event {ev} unknown")
            else:
                e = nodes[ev]
                if not (d(e["start"]) <= d(n["date"]) <= d(e["end"])):
                    errors.append(f"{fp}: day event {ev} not on {n['date']}")
        if n.get("stay") and n["stay"] not in nodes:
            errors.append(f"{fp}: day stay {n['stay']} unknown")

from collections import Counter
counts = Counter(n.get("type") for n in nodes.values())
print(f"{len(nodes)} nodes: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
print(f"{len(edges)} edges")
per_city = {}
for nid, n in nodes.items():
    if n.get("type") == "restaurant":
        city = n.get("place", "").split("/")[-1]
        per_city.setdefault(city, [0, 0])
        per_city[city][0] += 1
strict = set()
from common import strict_restaurants
strict = set(strict_restaurants(nodes))
for nid in strict:
    city = nodes[nid].get("place", "").split("/")[-1]
    per_city.setdefault(city, [0, 0])[1] += 1
print("restaurants per city (total / strict >=3.5 & <5000 yen): " +
      ", ".join(f"{c}: {t}/{s}" for c, (t, s) in sorted(per_city.items())))
if errors:
    print(f"\n{len(errors)} ERRORS:")
    for e in sorted(errors)[:60]:
        print(" -", e)
    sys.exit(1)
print("\nGraph consistent")
