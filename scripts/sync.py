"""Keep the repository consistent: create missing trip day files, normalize every node's
frontmatter (schema key order, no empty optional keys), regenerate the `<!-- gen:start X -->`
blocks of READMEs and day files, and rebuild exports/.

    python3 scripts/sync.py           # write changes
    python3 scripts/sync.py --check   # CI: exit 1 if anything would change
"""
import argparse
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exporters as X  # noqa: E402
import fm as fmio  # noqa: E402
from common import (REPO, canonical, city_children, d, day_id, daterange, derive_edges, derive_fields,  # noqa: E402
                    expected_day,
                    load_graph, read, strict_restaurants, trip_day_ids, trip_window, write)
from tripplan import load_profile, trip_view  # noqa: E402
from datetime import timedelta  # noqa: E402

GEN = re.compile(r"(<!-- gen:start ([a-z][a-z-]*) -->)(.*?)(<!-- gen:end \2 -->)", re.S)
EXPORT_EXT = (".json", ".geojson", ".ics", ".html")


def replace_blocks(text, blocks):
    def rep(m):
        name = m.group(2)
        if name not in blocks:
            return m.group(0)
        content = blocks[name].strip("\n")
        return f"{m.group(1)}\n{content}\n{m.group(4)}" if content else f"{m.group(1)}\n{m.group(4)}"
    return GEN.sub(rep, text)


def link(from_fp, to_fp):
    return os.path.relpath(to_fp, os.path.dirname(from_fp)).replace(os.sep, "/")


def _yen(x):
    return "—" if x is None else f"¥{x:,}"


# ---------------------------------------------------------------- generated blocks

def city_blocks(n, nodes, paths):
    rows = []
    for nid in city_children(nodes, n["path"], ("restaurant",)):
        r = nodes[nid]
        area = nodes.get(r.get("area"), {}).get("name", r.get("area", ""))
        extra = f", Tabelog {r['tabelog_rating']}" if r.get("tabelog_rating") is not None else ""
        rows.append(f"- [{r['name']}]({link(n['_fp'], r['_fp'])}) — {r.get('cuisine', '')}, "
                    f"{r.get('price_range', '')}, {area}{extra}")
    rows.sort(key=str.lower)
    routes = []
    for rid, r in sorted(nodes.items()):
        if r.get("type") == "route" and n["path"] in (r.get("origin"), r.get("destination")):
            dur = f" (~{r['duration_hours']} h)" if r.get("duration_hours") else ""
            routes.append(f"- [{r['name']}]({link(n['_fp'], r['_fp'])}) — {r.get('approx_cost', '')}{dur}")
    return {"restaurants": "\n" + "\n".join(rows) + "\n", "routes": "\n".join(routes) or "(none yet)"}


def day_blocks(day, view, nodes):
    lines = []
    for e in view["events"]:
        lines.append(f"- [{e['name']}]({link(day['_fp'], nodes[e['id']]['_fp'])}) ({e['start']} → {e['end']})"
                     + (" — in plan" if e["in_plan"] else ""))
    return {"events": "\n".join(lines) or "(none)"}


def trip_blocks(trip, view, nodes):
    ev = ["| Dates | Event | City | Our days there | In plan |", "|---|---|---|---|---|"]
    for e in view["events"]:
        ours = _ranges(e["our_days"]) or "—"
        ev.append(f"| {e['start']} → {e['end']} | [{e['name']}]({link(trip['_fp'], nodes[e['id']]['_fp'])}) | "
                  f"{e['place'].split('/')[-1].capitalize()} | {ours} | {', '.join(x[5:] for x in e['in_plan']) or '—'} |")
    b = view["budget"].get("daily_yen")
    bud = [f"Daily budget: {_yen(b)} per person (€{view['budget'].get('daily_eur_per_person')} × "
           f"{view['budget'].get('eur_jpy')} ECB {view['budget'].get('eur_jpy_date')}).", "",
           "| Date | City | Planned | vs budget | Spent | Unpriced items |", "|---|---|---|---|---|---|"]
    for v in view["days"]:
        diff = "" if not b else (f"+{_yen(v['est_yen'] - b)}" if v["est_yen"] > b else "ok")
        bud.append(f"| {v['date']} {v['weekday']} | {v['city'] or ''} | {_yen(v['est_yen'])} | {diff} | "
                   f"{_yen(v['spent_yen'])} | {', '.join(v['unpriced']) or ''} |")
    t = view["totals"]
    bud.append(f"| **total** | | **{_yen(t['est_yen'])}** | {_yen(t['budget_yen'])} budget | {_yen(t['spent_yen'])} | |")
    dl = []
    for x in view["deadlines"]:
        if x["kind"] in ("on_sale", "presale"):
            what = "tickets on sale" if x["kind"] == "on_sale" else "pre-sale lottery opens"
            dl.append(f"- [ ] **{x['when'].replace('T', ' ')}** — {what}: {x['name']} ({x.get('note') or ''})")
        else:
            dl.append(f"- [ ] **{x['date']}** — book {x['name']} for {x['for']} ({x['booking']}, {x['lead_days']} days ahead)")
    days = ["| Date | City | Title | Plan | Est. |", "|---|---|---|---|---|"]
    for v in view["days"]:
        warn = " ⚠" if v["warnings"] or any(i.get("closed") for i in v["items"]) else ""
        names = "; ".join(i["name"] for i in v["items"])
        days.append(f"| [{v['date']}]({link(trip['_fp'], nodes[v['id']]['_fp'])}) {v['weekday']} | {v['city'] or ''} | "
                    f"{v.get('title') or ''}{warn} | {names} | {_yen(v['est_yen'])} |")
    rated = sorted(((x["rating"], v["date"], x["id"], x.get("note")) for v in view["days"] for x in v["done"]
                    if isinstance(x, dict) and x.get("rating") is not None), key=lambda r: (-r[0], r[1], r[2]))
    liked = [f"- {'★' * r} {nodes[i]['name']} ({dt}){' — ' + note if note else ''}" for r, dt, i, note in rated
             if i in nodes]
    return {"events": "\n".join(ev), "budget": "\n".join(bud), "deadlines": "\n".join(dl) or "(none)",
            "days": "\n".join(days),
            "liked": "\n".join(liked) or "(nothing rated yet — after each day: `python3 scripts/log.py done --trip "
                                         f"{trip['id']} --date YYYY-MM-DD --id <node> --rating 1-5`)"}


def _ranges(dates):
    if not dates:
        return ""
    out, a, prev = [], dates[0], dates[0]
    for x in dates[1:] + [None]:
        if x and d(x) == d(prev) + timedelta(days=1):
            prev = x
            continue
        out.append(a[5:] if a == prev else f"{a[5:]}–{prev[5:]}")
        if x:
            a = prev = x
    return ", ".join(out)


def catalog_block(nodes, edges):
    counts = Counter(n.get("type") for n in nodes.values())
    strict = set(strict_restaurants(nodes))
    per_city = {}
    for nid, n in nodes.items():
        if n.get("type") == "restaurant":
            c = per_city.setdefault(n["place"].split("/")[-1], [0, 0])
            c[0] += 1
            c[1] += nid in strict
    with_coords = sum(1 for n in nodes.values() if n.get("coords") and n.get("type") in
                      ("activity", "restaurant", "hotel", "area", "event"))
    leaves = sum(1 for n in nodes.values() if n.get("type") in ("activity", "restaurant", "hotel", "area", "event"))
    return "\n".join([
        "", "## Catalog size (generated by `scripts/sync.py` — do not edit by hand)", "",
        f"- Nodes: {len(nodes)} (" + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) + f"); edges: {len(edges)}",
        "- Restaurants per city (total / Tabelog >= 3.5 with a meal <= ¥4,999/person): "
        + ", ".join(f"{c}: {t}/{s}" for c, (t, s) in sorted(per_city.items())),
        f"- Geolocated places: {with_coords}/{leaves} (OpenStreetMap)", ""])


# ---------------------------------------------------------------- run

def new_day_node(trip, day, nodes, paths):
    place, stay = expected_day(trip, day)
    city = nodes.get(paths.get(place), {}).get("name", "")
    fp = os.path.join(os.path.dirname(trip["_fp"]), "days", f"{d(day).isoformat()}.md")
    body = (f"\n# {d(day).isoformat()} — {city}\n\n## Itinerary\n\n## Events today\n\n"
            "<!-- gen:start events -->\n<!-- gen:end events -->\n\n## Notes\n")
    n = {"id": day_id(trip["id"], day), "type": "day", "date": d(day), "trip": trip["id"], "place": place}
    if stay:
        n["stay"] = stay
    n.update(_fp=fp, _body=body)
    return n


def build(root=REPO):
    """Return ({abs_path: content}, [log lines]) or raise SystemExit on unloadable graph."""
    errors = []
    nodes, paths, edges = load_graph(root, errors)
    if errors:
        print("Cannot sync — fix these first (scripts/validate_graph.py has details):")
        for e in errors:
            print(" -", e)
        raise SystemExit(1)
    log = []
    for tid, t in sorted(nodes.items()):
        if t.get("type") != "trip":
            continue
        a, b = trip_window(t)
        for day in daterange(a, b + timedelta(days=1)):
            did = day_id(tid, day)
            if did not in nodes:
                nodes[did] = new_day_node(t, day, nodes, paths)
                log.append(f"new day file {did}")
        t["days"] = trip_day_ids(t)
    # work on the canonical form so exports match what the files will contain after this run
    nodes = {nid: dict(canonical(derive_fields(n)), _fp=n["_fp"], _body=n["_body"]) for nid, n in nodes.items()}
    edges = derive_edges(nodes, paths)
    profile = load_profile(root)
    views = {tid: trip_view(nodes, paths, t, profile) for tid, t in nodes.items() if t.get("type") == "trip"}
    day_views = {v["id"]: v for tv in views.values() for v in tv["days"]}

    files = {}
    for nid, n in nodes.items():
        body = n["_body"]
        t = n.get("type")
        if t == "city":
            body = replace_blocks(body, city_blocks(n, nodes, paths))
        elif t == "day" and nid in day_views:
            body = replace_blocks(body, day_blocks(n, day_views[nid], nodes))
        elif t == "trip":
            body = replace_blocks(body, trip_blocks(n, views[nid], nodes))
        files[n["_fp"]] = fmio.render(canonical(n), body)

    readme = os.path.join(root, "README.md")
    if os.path.exists(readme):
        files[readme] = replace_blocks(read(readme), {"catalog": catalog_block(nodes, edges)})

    ex = os.path.join(root, "exports")
    files[os.path.join(ex, "index.json")] = X.build_index(nodes, edges)
    for cid, c in sorted(nodes.items()):
        if c.get("type") != "city":
            continue
        files[os.path.join(ex, "cities", f"{cid}.json")] = X.build_city(nodes, paths, edges, cid)
        files[os.path.join(ex, "shortlists", f"{cid}.json")] = X.build_shortlist(nodes, paths, edges, cid)
        gj = X.build_city_geojson(nodes, paths, cid)
        if gj:
            files[os.path.join(ex, "maps", f"{cid}.geojson")] = gj
    for tid, view in sorted(views.items()):
        t = nodes[tid]
        files[os.path.join(ex, "trips", f"{tid}.json")] = X.build_trip_json(nodes, t, view)
        files[os.path.join(ex, "trips", f"{tid}.ics")] = X.build_ics(t, view)
        bodies = {x: nodes[x]["_body"] for x in t.get("days") or [] if x in nodes}
        files[os.path.join(ex, "trips", f"{tid}.html")] = X.build_html(t, view, bodies)
        gj = X.build_trip_geojson(nodes, view)
        if gj:
            files[os.path.join(ex, "trips", f"{tid}.geojson")] = gj
    return files, log


def orphans(root, files):
    ex = os.path.join(root, "exports")
    out = []
    for dirpath, _, fnames in os.walk(ex):
        for f in fnames:
            fp = os.path.join(dirpath, f)
            if f.endswith(EXPORT_EXT) and fp not in files:
                out.append(fp)
    return sorted(out)


def run(root=REPO, check=False):
    files, log = build(root)
    stale = [fp for fp, content in sorted(files.items())
             if not os.path.exists(fp) or read(fp) != content]
    gone = orphans(root, files)
    rel = lambda p: os.path.relpath(p, root)
    if check:
        if stale or gone:
            print("STALE — run `python3 scripts/sync.py` and commit the result:")
            for fp in stale:
                print(" -", rel(fp))
            for fp in gone:
                print(" - (orphan)", rel(fp))
            return 1
        print("Nodes, generated blocks and exports are up to date")
        return 0
    for fp in stale:
        write(fp, files[fp])
    for fp in gone:
        os.remove(fp)
    for line in log:
        print(line)
    print(f"{len(files)} files checked: {len(stale)} written, {len(gone)} orphan exports removed")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="do not write; exit 1 if anything is stale")
    ap.add_argument("--root", default=REPO, help=argparse.SUPPRESS)
    a = ap.parse_args()
    sys.exit(run(a.root, a.check))
