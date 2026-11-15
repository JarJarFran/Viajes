import json, os, re, sys
from datetime import date, timedelta
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import REPO, SCHEMA, load_graph, parse_node, public, city_children, strict_restaurants, d

GEO_STRIP = set(SCHEMA["geo_strip_keys"])
OPTIONAL = set(SCHEMA["optional_keys"])
REQ = {t: set(spec["required"]) for t, spec in SCHEMA["types"].items()}
GEN_START = "<!-- gen:start"
GEN_END = "<!-- gen:end"


def normalize_file(text, fm):
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text, False
    t = fm.get("type")
    out, changed = [], False
    for line in parts[1].split("\n"):
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not m:
            out.append(line)
            continue
        key, val = m.group(1), m.group(2).split("#")[0].strip()
        if t in ("country", "region", "city") and key in GEO_STRIP:
            changed = True
            continue
        if key in OPTIONAL and key not in REQ.get(t, ()) and val in ("[]", "null", '""', "''"):
            changed = True
            continue
        out.append(line)
    if not changed:
        return text, False
    return "---" + "\n".join(out) + "---" + parts[2], True


def ensure_days(nodes, paths):
    created = []
    for nid, n in sorted(nodes.items()):
        if n.get("type") != "trip":
            continue
        start, end = d(n["start"]), d(n["end"])
        day_ids = []
        day = start
        while day <= end and len(day_ids) < 400:
            did = f"day-{day.isoformat()}"
            day_ids.append(did)
            fp = os.path.join(os.path.dirname(n["_fp"]), "days", did + ".md")
            if not os.path.exists(fp):
                stop = next((s for s in n.get("stops", []) if d(s["from"]) <= day <= d(s["to"])), None)
                place = stop["place"] if stop else ""
                stay = stop.get("accommodation", "") if stop else ""
                evs = sorted(eid for eid, e in nodes.items()
                             if e.get("type") == "event" and e.get("place") == place
                             and d(e["start"]) <= day <= d(e["end"]))
                city_name = place.split("/")[-1].capitalize() if place else ""
                lines = ["---",
                         f"id: {did}",
                         "type: day",
                         f"date: {day.isoformat()}",
                         f"trip: {nid}",
                         f"place: {place}"]
                if stay:
                    lines.append(f"stay: {stay}")
                lines += ["plan: []",
                          "events: [" + ", ".join(evs) + "]",
                          "---",
                          "",
                          f"# {day.isoformat()} — {city_name}",
                          "",
                          "## Plan (fill `plan:` with activity/restaurant ids)",
                          "",
                          "## Notes",
                          ""]
                os.makedirs(os.path.dirname(fp), exist_ok=True)
                open(fp, "w", encoding="utf-8").write("\n".join(lines))
                created.append(did)
            day += timedelta(days=1)
        text = open(n["_fp"], encoding="utf-8").read()
        if "days:" not in text.split("---", 2)[1]:
            fm_text = text.split("---", 2)[1]
            new_fm = fm_text.rstrip("\n") + "\ndays: [" + ", ".join(day_ids) + "]\n"
            open(n["_fp"], "w", encoding="utf-8").write("---" + new_fm + "---" + text.split("---", 2)[2])
    return created


def restaurant_section_lines(nodes, city_path, folder):
    rdir = None
    for nid in city_children(nodes, city_path):
        fp = nodes[nid]["_fp"]
        rdir = os.path.dirname(fp)
    entries = []
    for nid in city_children(nodes, city_path):
        if nodes[nid].get("type") != "restaurant":
            continue
        fm = nodes[nid]
        rel = "restaurants/" + os.path.basename(fm["_fp"])
        extra = f", Tabelog {fm['tabelog_rating']}" if fm.get("tabelog_rating") is not None else ""
        entries.append(f"- [{fm['name']}]({rel}) — {fm.get('cuisine','')}, {fm.get('price_range','')}, {fm.get('area','')}{extra}")
    entries.sort(key=str.lower)
    return entries


def regen_readme_sections(nodes, paths):
    changed = []
    for nid, n in sorted(nodes.items()):
        if n.get("type") != "city":
            continue
        fp = n["_fp"]
        text = open(fp, encoding="utf-8").read()
        lines = text.split("\n")
        title = "## Restaurants" if any(l.strip() == "## Restaurants" for l in lines) else "## Where to eat"
        if not any(l.strip() == title for l in lines):
            continue
        start = next(i for i, l in enumerate(lines) if l.strip() == title)
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
        inner = lines[start + 1:end]
        has_markers = any(GEN_START in l for l in inner)
        if has_markers:
            b = next(i for i, l in enumerate(inner) if GEN_START in l)
            e = next(i for i, l in enumerate(inner) if GEN_END in l)
            body = inner[b + 1:e]
        else:
            body = [l for l in inner if l.strip()]
        new_entries = restaurant_section_lines(nodes, n["path"], "restaurants")
        if body == new_entries and has_markers:
            continue
        new_inner = inner[:0]
        pre = [] if has_markers else [l for l in inner if not l.strip().startswith("- [")]
        sec = pre + ["", f"{GEN_START} restaurants -->", ""] + new_entries + ["", f"{GEN_END} restaurants -->"]
        if has_markers:
            sec = inner[:b] + [f"{GEN_START} restaurants -->", ""] + new_entries + ["", f"{GEN_END} restaurants -->"] + inner[e + 1:]
        lines = lines[:start + 1] + sec + lines[end:]
        open(fp, "w", encoding="utf-8").write("\n".join(lines))
        changed.append(nid)
    return changed


def readme_catalog_block(nodes, paths, edges):
    from collections import Counter
    counts = Counter(n.get("type") for n in nodes.values())
    per_city = {}
    strict = set(strict_restaurants(nodes))
    for nid, n in nodes.items():
        if n.get("type") == "restaurant":
            city = n.get("place", "").split("/")[-1]
            per_city.setdefault(city, [0, 0])
            per_city[city][0] += 1
            if nid in strict:
                per_city[city][1] += 1
    lines = [f"{GEN_START} catalog -->", "",
             "## Catalog size (generated by `scripts/sync.py` — do not edit by hand)", "",
             f"- Nodes: {len(nodes)} (" + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) + f"); edges: {len(edges)}",
             "- Restaurants per city (total / Tabelog >= 3.5 and < ¥5,000/person): " +
             ", ".join(f"{c}: {t}/{s}" for c, (t, s) in sorted(per_city.items())), "",
             f"{GEN_END} catalog -->"]
    return "\n".join(lines)


def update_root_readme(nodes, paths, edges):
    fp = os.path.join(REPO, "README.md")
    text = open(fp, encoding="utf-8").read()
    block = readme_catalog_block(nodes, paths, edges)
    if f"{GEN_START} catalog -->" in text:
        text = re.sub(r"<!-- gen:start catalog -->.*?<!-- gen:end catalog -->", lambda m: block, text, flags=re.S)
    else:
        text = text.rstrip("\n") + "\n\n" + block + "\n"
    text = re.sub(r"\nCurrent restaurant catalog \(scores read on tabelog\.com/en category lists, 2026-11\):.*\n", "\n", text)
    open(fp, "w", encoding="utf-8").write(text)


def build_exports(nodes, paths, edges):
    exp = os.path.join(REPO, "exports")
    os.makedirs(exp, exist_ok=True)
    files = {}
    counts = {}
    for nid, n in nodes.items():
        counts[n.get("type")] = counts.get(n.get("type"), 0) + 1
    index = {"schema": 1, "counts": dict(sorted(counts.items())),
             "nodes": {nid: public(nodes[nid]) for nid in sorted(nodes)},
             "edges": edges}
    files["exports/index.json"] = json.dumps(index, ensure_ascii=False, separators=(",", ":"), default=str) + "\n"
    for cpath, cid in sorted(paths.items()):
        if nodes[cid].get("type") != "city":
            continue
        kids = set(city_children(nodes, cpath)) | {cid}
        cedges = [e for e in edges if e["from"] in kids and e["to"] in kids]
        ancestors = []
        a = nodes[cid].get("region")
        while a in nodes:
            ancestors.append(a)
            a = nodes[a].get("region") or (nodes[a].get("country") if nodes[a].get("type") == "region" else None)
        if nodes[cid].get("country") in nodes:
            ancestors.append(nodes[cid]["country"])
        cdata = {"schema": 1, "city": cpath, "ancestors": ancestors,
                 "nodes": {nid: public(nodes[nid]) for nid in sorted(kids)},
                 "edges": cedges}
        files[f"exports/cities/{cid}.json"] = json.dumps(cdata, ensure_ascii=False, separators=(",", ":"), default=str) + "\n"
        strict = [nid for nid in strict_restaurants(nodes) if nodes[nid].get("place") == cpath]
        acts = [nid for nid in city_children(nodes, cpath)
                if nodes[nid].get("type") == "activity" and ({"top50", "top100"} & set(nodes[nid].get("tags") or []))]
        evs = [nid for nid in city_children(nodes, cpath) if nodes[nid].get("type") == "event"]
        sl = {"city": cpath,
              "activities_top": [{k: nodes[a].get(k) for k in ("id", "name", "category", "entry", "tags", "approx_cost", "hours", "booking", "duration_hours")} for a in sorted(acts)],
              "restaurants_strict": [{k: nodes[r].get(k) for k in ("id", "name", "cuisine", "area", "price_range", "tabelog_rating")} for r in strict],
              "events": [{k: nodes[e].get(k) for k in ("id", "name", "start", "end", "entry", "approx_cost")} for e in sorted(evs)]}
        files[f"exports/shortlists/{cid}.json"] = json.dumps(sl, ensure_ascii=False, indent=2, default=str) + "\n"
    for nid, n in sorted(nodes.items()):
        if n.get("type") != "trip":
            continue
        day_ids = [x for x in n.get("days") or []]
        ids = {nid} | set(day_ids)
        tedges = [e for e in edges if e["from"] in ids or e["to"] in ids]
        related = {}
        for e in tedges:
            for end in (e["from"], e["to"]):
                if end in nodes and end not in ids:
                    related[end] = {"type": nodes[end].get("type"), "name": nodes[end].get("name")}
        tdata = {"schema": 1, "trip": nid, "trip_node": public(n),
                 "days": {x: public(nodes[x]) for x in day_ids if x in nodes},
                 "edges": tedges, "related": dict(sorted(related.items()))}
        files[f"exports/trips/{nid}.json"] = json.dumps(tdata, ensure_ascii=False, separators=(",", ":"), default=str) + "\n"
    return files


def run(check=False):
    nodes, paths, edges = load_graph()
    changed_nodes = []
    for nid, n in sorted(nodes.items()):
        text = open(n["_fp"], encoding="utf-8").read()
        new, changed = normalize_file(text, n)
        if changed:
            if check:
                changed_nodes.append(nid)
            else:
                open(n["_fp"], "w", encoding="utf-8").write(new)
    if not check:
        nodes, paths, edges = load_graph()
        created_days = ensure_days(nodes, paths)
        nodes, paths, edges = load_graph()
        regen = regen_readme_sections(nodes, paths)
        update_root_readme(nodes, paths, edges)
        print(f"created {len(created_days)} day files, refreshed README sections: {len(regen)} cities")
    files = build_exports(nodes, paths, edges)
    stale = []
    for rel, content in sorted(files.items()):
        fp = os.path.join(REPO, rel)
        if not os.path.exists(fp) or open(fp, encoding="utf-8").read() != content:
            stale.append(rel)
            if not check:
                os.makedirs(os.path.dirname(fp), exist_ok=True)
                open(fp, "w", encoding="utf-8").write(content)
    if check:
        if changed_nodes:
            stale += [f"node:{n}" for n in changed_nodes]
        if stale:
            print("STALE (run `python3 scripts/sync.py`):")
            for s in stale:
                print(" -", s)
            sys.exit(1)
        print("Exports and node normalization up to date")
    else:
        print(f"wrote {len(files)} export files" + (f" ({len(stale)} updated)" if stale else ""))


if __name__ == "__main__":
    run(check="--check" in sys.argv)
