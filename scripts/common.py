import os, re, yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = yaml.safe_load(open(os.path.join(REPO, "schema.yaml"), encoding="utf-8"))
LIST_EDGE_KEYS = ["near", "done_in"]
PRICE_MAX_YEN = {"¥": 999, "¥¥": 2999, "¥¥¥": 4999, "¥¥¥¥": 10**9}


def iter_node_files():
    for base in ("destinations", "trips"):
        for root, dirs, files in os.walk(os.path.join(REPO, base)):
            dirs[:] = [d for d in dirs if d != ".git"]
            for f in sorted(files):
                if f.endswith(".md"):
                    yield os.path.join(root, f)


def parse_node(fp):
    text = open(fp, encoding="utf-8").read()
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    fm["_fp"] = fp
    fm["_body"] = parts[2]
    return fm


def public(fm):
    return {k: v for k, v in fm.items() if not k.startswith("_")}


def load_graph():
    nodes, paths = {}, {}
    for fp in iter_node_files():
        fm = parse_node(fp)
        if fm is None or "id" not in fm:
            continue
        nodes[fm["id"]] = fm
        if "path" in fm:
            paths[fm["path"]] = fm["id"]
    edges = []

    def add(a, b, rel, **meta):
        if a in nodes and b in nodes:
            e = {"from": a, "to": b, "rel": rel}
            e.update(meta)
            edges.append(e)

    for nid, n in nodes.items():
        t = n.get("type")
        if n.get("place") in paths:
            add(nid, paths[n["place"]], "place")
        if n.get("country") in nodes:
            add(nid, n["country"], "country")
        if n.get("region") in nodes:
            add(nid, n["region"], "region")
        p = n.get("path")
        if p and "/" in p:
            parent = p.rsplit("/", 1)[0]
            if parent in paths:
                add(nid, paths[parent], "contains")
        for k in LIST_EDGE_KEYS:
            for v in n.get(k) or []:
                add(nid, v, k)
        if t == "trip":
            for s in n.get("stops", []):
                if s.get("place") in paths:
                    add(nid, paths[s["place"]], "stop", **{"from": str(s.get("from")), "to": str(s.get("to"))})
                if s.get("accommodation"):
                    add(nid, s["accommodation"], "stay")
                for a in s.get("activities") or []:
                    add(nid, a, "candidate")
            for ev in n.get("events") or []:
                add(nid, ev, "event")
            for d in n.get("days") or []:
                add(nid, d, "day")
        if t == "day":
            if n.get("trip") in nodes:
                add(nid, n["trip"], "day")
            if n.get("place") in paths:
                add(nid, paths[n["place"]], "place")
            if n.get("stay"):
                add(nid, n["stay"], "stay")
            for a in n.get("plan") or []:
                add(nid, a, "plan")
            for ev in n.get("events") or []:
                add(nid, ev, "event")
    edges.sort(key=lambda e: (e["from"], e["rel"], e["to"]))
    return nodes, paths, edges


def city_children(nodes, city_path):
    return sorted(nid for nid, n in nodes.items() if n.get("place") == city_path)


def strict_restaurants(nodes):
    out = []
    for nid, n in sorted(nodes.items()):
        if n.get("type") != "restaurant":
            continue
        r = n.get("tabelog_rating")
        if r is not None and float(r) >= 3.5 and n.get("price_range") in ("¥", "¥¥", "¥¥¥"):
            out.append(nid)
    return out


def d(s):
    from datetime import date
    return date.fromisoformat(str(s)[:10])
