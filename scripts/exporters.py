"""Builders for everything under exports/: diff-friendly JSON, GeoJSON maps, the trip calendar
(.ics) and the offline trip page (.html). All output is deterministic (no clocks, sorted keys)
so `sync.py --check` can compare it byte for byte."""
import html
import json
import math
import re
from datetime import datetime, timedelta, timezone

from common import (SCHEMA, ancestors, area_of, city_children, coords, d, public, strict_restaurants)

DTSTAMP = "20260101T000000Z"
TYPE_STYLE = {  # simplestyle-spec properties rendered by GitHub's map viewer
    "activity": ("#d1495b", "star"), "event": ("#8f2d56", "theatre"), "restaurant": ("#edae49", "restaurant"),
    "hotel": ("#00798c", "lodging"), "area": ("#7a7a7a", "circle-stroked")}
DAY_COLORS = ["#d1495b", "#00798c", "#edae49", "#30638e", "#8f2d56", "#66a182", "#003d5b"]


# ---------------------------------------------------------------- JSON

def _c(v):
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"), default=str)


def json_records(obj):
    """Valid JSON with one record per line: dicts of dicts / lists of dicts are expanded."""
    lines = ["{"]
    items = list(obj.items())
    for i, (k, v) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        if isinstance(v, dict) and v and all(isinstance(x, dict) for x in v.values()):
            sub = list(v.items())
            lines.append(f"{_c(k)}:{{")
            lines += [f"{_c(kk)}:{_c(vv)}" + ("," if j < len(sub) - 1 else "") for j, (kk, vv) in enumerate(sub)]
            lines.append("}" + comma)
        elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            lines.append(f"{_c(k)}:[")
            lines += [_c(x) + ("," if j < len(v) - 1 else "") for j, x in enumerate(v)]
            lines.append("]" + comma)
        else:
            lines.append(f"{_c(k)}:{_c(v)}{comma}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def build_index(nodes, edges):
    counts = {}
    for n in nodes.values():
        counts[n.get("type")] = counts.get(n.get("type"), 0) + 1
    return json_records({"schema": SCHEMA["version"], "counts": dict(sorted(counts.items())),
                         "nodes": {nid: public(nodes[nid]) for nid in sorted(nodes)}, "edges": edges})


def build_city(nodes, paths, edges, cid):
    cpath = nodes[cid]["path"]
    kids = set(city_children(nodes, cpath)) | {cid}
    routes = {nid for nid, n in nodes.items() if n.get("type") == "route"
              and cpath in (n.get("origin"), n.get("destination"))}
    ids = kids | routes
    return json_records({"schema": SCHEMA["version"], "city": cpath, "ancestors": ancestors(nodes, cid),
                         "nodes": {nid: public(nodes[nid]) for nid in sorted(ids)},
                         "edges": [e for e in edges if e["from"] in ids and e["to"] in ids]})


def build_shortlist(nodes, paths, edges, cid):
    cpath = nodes[cid]["path"]
    kids = city_children(nodes, cpath)
    strict = [r for r in strict_restaurants(nodes) if nodes[r].get("place") == cpath]
    pick = lambda n, ks: {k: n[k] for k in ks if n.get(k) not in (None, "", [])}
    acts = [nodes[a] for a in kids if nodes[a]["type"] == "activity"
            and {"top50", "top100"} & set(nodes[a].get("tags") or [])]
    data = {
        "city": cpath,
        "areas": [pick(nodes[a], ("id", "name", "coords")) for a in kids if nodes[a]["type"] == "area"],
        "activities_top": [dict(pick(n, ("id", "name", "category", "entry", "cost_yen", "tags", "hours", "booking",
                                         "duration_hours")), area=area_of(n["id"], nodes, edges),
                                closed=[c for c in n.get("closed") or []]) for n in acts],
        "restaurants_strict": [pick(nodes[r], ("id", "name", "cuisine", "area", "price_range", "budget_lunch_yen",
                                               "budget_dinner_yen", "budget_yen", "tabelog_rating", "station"))
                               for r in strict],
        "events": [pick(nodes[e], ("id", "name", "recurrence", "editions", "entry", "cost_yen")) for e in kids
                   if nodes[e]["type"] == "event"],
        "routes": [pick(n, ("id", "name", "origin", "destination", "mode", "duration_hours", "price_yen"))
                   for nid, n in sorted(nodes.items()) if n.get("type") == "route"
                   and cpath in (n.get("origin"), n.get("destination"))],
    }
    for a in data["activities_top"]:
        if not a["closed"]:
            a.pop("closed")
        if not a["area"]:
            a.pop("area")
    return json.dumps(data, ensure_ascii=False, indent=1, default=str) + "\n"


def build_trip_json(nodes, trip, view):
    days = {x: public(nodes[x]) for x in trip.get("days") or [] if x in nodes}
    related = {}
    for v in view["days"]:
        for it in v["items"]:
            related[it["id"]] = it["type"]
    return json_records({"schema": SCHEMA["version"], "trip": trip["id"], "trip_node": public(trip),
                         "summary": {k: view[k] for k in ("name", "start", "end", "nights", "budget", "totals")},
                         "deadlines": view["deadlines"], "events": view["events"],
                         "days": {v["id"]: v for v in view["days"]}, "day_nodes": days,
                         "related": dict(sorted(related.items()))})


# ---------------------------------------------------------------- GeoJSON

def _feature(n, extra=None):
    c = coords(n)
    color, symbol = TYPE_STYLE.get(n["type"], ("#555555", "marker"))
    desc = []
    if n["type"] == "restaurant":
        desc = [n.get("cuisine"), n.get("price_range"), f"Tabelog {n['tabelog_rating']}" if n.get("tabelog_rating") else None,
                f"near {n['station']} Sta. ({n.get('station_m')} m)" if n.get("station") else None]
    elif n["type"] in ("activity", "event"):
        desc = [n.get("category"), n.get("approx_cost"), n.get("hours")]
    elif n["type"] == "hotel":
        desc = [n.get("price_range"), n.get("area_detail")]
    props = {"id": n["id"], "type": n["type"], "title": n.get("name"),
             "description": " · ".join(str(x) for x in desc if x),
             "marker-color": color, "marker-symbol": symbol, "marker-size": "small" if n["type"] == "restaurant" else "medium"}
    if n.get("coords_precision") and n["coords_precision"] != "exact":
        props["precision"] = n["coords_precision"]
    props.update(extra or {})
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(c[1], 6), round(c[0], 6)]},
            "properties": props}


def _collection(features):
    lines = ['{"type":"FeatureCollection","features":[']
    lines += [_c(f) + ("," if i < len(features) - 1 else "") for i, f in enumerate(features)]
    lines.append("]}")
    return "\n".join(lines) + "\n"


def build_city_geojson(nodes, paths, cid):
    cpath = nodes[cid]["path"]
    feats = [_feature(nodes[x]) for x in city_children(nodes, cpath) if coords(nodes[x])]
    return _collection(feats) if feats else None


def build_trip_geojson(nodes, view):
    feats = []
    for i, v in enumerate(view["days"]):
        color = DAY_COLORS[i % len(DAY_COLORS)]
        pts = []
        if v["stay"] and v["stay"].get("coords"):
            pts.append(v["stay"]["coords"])
        for k, it in enumerate(v["items"], 1):
            if it.get("coords"):
                pts.append(it["coords"])
                feats.append(_feature(nodes[it["id"]], {"day": v["date"], "slot": it.get("slot"), "order": k,
                                                         "marker-color": color,
                                                         "title": f"{v['date']} #{k} {it['name']}"}))
        if len(pts) > 1:
            feats.append({"type": "Feature", "geometry": {"type": "LineString",
                                                          "coordinates": [[round(p[1], 6), round(p[0], 6)] for p in pts]},
                          "properties": {"day": v["date"], "title": f"{v['date']} {v.get('title') or ''}".strip(),
                                         "stroke": color, "stroke-width": 3, "stroke-opacity": 0.8}})
    return _collection(feats) if feats else None


# ---------------------------------------------------------------- iCalendar

def _ics_text(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line):
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def _yen(x):
    return "?" if x is None else f"¥{x:,}"


def build_ics(trip, view):
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//viajes//travel-graph//EN", "CALSCALE:GREGORIAN",
         "METHOD:PUBLISH", f"X-WR-CALNAME:{_ics_text(trip.get('name'))}", "X-WR-TIMEZONE:Asia/Tokyo"]

    def event(uid, start_lines, summary, desc, location=None, alarms=()):
        L.extend(["BEGIN:VEVENT", f"UID:{uid}@viajes", f"DTSTAMP:{DTSTAMP}", *start_lines,
                  f"SUMMARY:{_ics_text(summary)}", f"DESCRIPTION:{_ics_text(desc)}"])
        if location:
            L.append(f"LOCATION:{_ics_text(location)}")
        for trig, text in alarms:
            L.extend(["BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER:{trig}", f"DESCRIPTION:{_ics_text(text)}", "END:VALARM"])
        L.append("END:VEVENT")

    for v in view["days"]:
        day = d(v["date"])
        lines = []
        for it in v["items"]:
            s = f"[{it.get('slot') or '-'}] {it['name']} ({_yen(it.get('est_yen'))})"
            if it.get("closed"):
                s += " — " + "; ".join(("PARTIAL: " + c["partial"]) if c.get("partial") else "CLOSED: " + c["rule"]
                                       for c in it["closed"])
            lines.append(s)
        if v["events"]:
            lines.append("Events: " + ", ".join(e["name"] for e in v["events"]))
        lines.append(f"Estimated {_yen(v['est_yen'])} / budget {_yen(v['budget_yen'])} per person")
        summary = f"{v['city'] or ''} · {v.get('title') or ''}".strip(" ·")
        event(v["id"], [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
                        "TRANSP:TRANSPARENT"],
              summary, "\n".join(lines), v["stay"]["name"] if v.get("stay") else None)
    for dl in view["deadlines"]:
        if dl["kind"] in ("on_sale", "presale"):
            when = datetime.fromisoformat(dl["when"]) if "T" in dl["when"] else None
            if when and when.tzinfo:
                u = when.astimezone(timezone.utc)
                start = [f"DTSTART:{u:%Y%m%dT%H%M%SZ}", f"DTEND:{u + timedelta(minutes=30):%Y%m%dT%H%M%SZ}"]
            else:
                day = d(dl["date"])
                start = [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
            label = "Tickets on sale" if dl["kind"] == "on_sale" else "Pre-sale lottery opens"
            event(f"{dl['id']}-{dl['kind'].replace('_', '-')}-{dl['date']}", start, f"🎟 {label}: {dl['name']}",
                  f"{dl.get('note') or ''}\nEdition {dl['for']}".strip(), None,
                  [("-P1D", f"Tomorrow: tickets for {dl['name']}"), ("-PT30M", f"In 30 min: tickets for {dl['name']}")])
        else:
            day = d(dl["date"])
            event(f"{dl['id']}-book-{dl['for']}", [f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
                                                   f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"],
                  f"Book: {dl['name']} (for {dl['for']})",
                  f"Booking {dl['booking']}; reminder {dl['lead_days']} days before the visit.", None,
                  [("PT9H", f"Book {dl['name']} for {dl['for']}")])
    L.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in L) + "\r\n"


# ---------------------------------------------------------------- offline HTML page

CSS = """
:root{--bg:#faf8f5;--card:#ffffff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e4e0da;--accent:#c0392b;--warn:#b7791f;--ok:#2f855a;--chip:#f1ede7}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1e1e22;--ink:#ececf0;--muted:#a0a0aa;--line:#33333a;--accent:#ff6b5b;--warn:#f0b429;--ok:#68d391;--chip:#2a2a30}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:760px;margin:0 auto;padding:16px}h1{font-size:1.4rem;margin:.2rem 0}h2{font-size:1.1rem;margin:1.6rem 0 .6rem}
.muted{color:var(--muted)}nav{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}nav a{background:var(--chip);border-radius:999px;padding:3px 9px;color:var(--ink);text-decoration:none;font-size:.85rem}
section.day{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:14px 0}
section.day h3{margin:0;font-size:1.05rem}.stay{font-size:.9rem;margin:.3rem 0 .6rem}
ol.items{padding-left:1.2rem;margin:.4rem 0}ol.items li{margin:.35rem 0}.slot{display:inline-block;min-width:5.8rem;margin-right:.3rem;font-size:.75rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.ja{font-size:.9rem}.badge{display:inline-block;font-size:.75rem;border-radius:6px;padding:0 6px;margin-left:4px}.closed{background:var(--accent);color:#fff}.partial{background:var(--warn);color:#000}
.cost{float:right;color:var(--muted);font-size:.85rem}a{color:var(--accent)}.over{color:var(--accent);font-weight:600}.under{color:var(--ok)}
svg{width:100%;height:auto;background:var(--chip);border-radius:8px;margin:.4rem 0}.notes{font-size:.9rem}.notes ul{padding-left:1.1rem;margin:.3rem 0}
table{border-collapse:collapse;width:100%;font-size:.9rem}td,th{border-bottom:1px solid var(--line);padding:4px 6px;text-align:left}
@media print{nav,svg{display:none}section.day{break-inside:avoid}}
"""


def _e(s):
    return html.escape(str(s), quote=True)


def _md_inline(s):
    s = _e(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", s)
    return s


def _body_html(body):
    body = re.sub(r"<!-- gen:start.*?gen:end [a-z]+ -->", "", body, flags=re.S)
    out, in_list = [], False
    for line in body.split("\n"):
        t = line.strip()
        if not t or t.startswith("# ") or (t.startswith("**") and t.endswith("**")) or t == "## Events today":
            continue
        if t.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_md_inline(t[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if t.startswith("## "):
            out.append(f"<h4>{_e(t[3:])}</h4>")
        else:
            out.append(f"<p>{_md_inline(t)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _svg_map(v):
    pts = []
    if v["stay"] and v["stay"].get("coords"):
        pts.append(("H", v["stay"]["coords"]))
    for k, it in enumerate(v["items"], 1):
        if it.get("coords"):
            pts.append((str(k), it["coords"]))
    if len(pts) < 2:
        return ""
    lat0 = sum(p[1][0] for p in pts) / len(pts)
    kx = math.cos(math.radians(lat0))
    xs = [p[1][1] * kx for p in pts]
    ys = [-p[1][0] for p in pts]
    w, h, pad = 320, 190, 18
    span = max(max(xs) - min(xs), max(ys) - min(ys), 0.004)
    sc = min((w - 2 * pad) / span, (h - 2 * pad) / span)
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    P = [(round(w / 2 + (x - cx) * sc, 1), round(h / 2 + (y - cy) * sc, 1)) for x, y in zip(xs, ys)]
    poly = " ".join(f"{x},{y}" for x, y in P)
    dots = "".join(
        f'<circle cx="{x}" cy="{y}" r="9" fill="{"#00798c" if lab == "H" else "#c0392b"}"/>'
        f'<text x="{x}" y="{y + 4}" font-size="10" text-anchor="middle" fill="#fff">{lab}</text>'
        for (lab, _), (x, y) in zip(pts, P))
    km = span * 111  # degrees -> km (x already scaled by cos(lat))
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Schematic map of the day ({km:.1f} km across)">'
            f'<polyline points="{poly}" fill="none" stroke="#888" stroke-width="2" stroke-dasharray="4 3"/>{dots}</svg>')


def build_html(trip, view, day_bodies):
    v0 = view
    budget = v0["budget"].get("daily_yen")
    H = ["<!doctype html>", '<html lang="en"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         f"<title>{_e(trip.get('name'))}</title><style>{CSS}</style></head><body><main>",
         f"<h1>{_e(trip.get('name'))}</h1>",
         f'<p class="muted">{_e(v0["start"])} → {_e(v0["end"])} · nights: '
         + ", ".join(f"{_e(p.split('/')[-1].capitalize())} {n}" for p, n in v0["nights"].items())
         + (f" · budget ¥{budget:,}/person/day (hotels excluded)" if budget else "") + "</p>",
         "<p class=\"muted\">Generated by scripts/sync.py — works offline. Map links need data.</p>"]
    H.append("<nav>" + "".join(f'<a href="#d-{_e(v["date"])}">{_e(v["date"][5:])}</a>' for v in v0["days"]) + "</nav>")
    if v0["deadlines"]:
        H.append("<h2>Deadlines</h2><table><tr><th>When</th><th>What</th></tr>")
        for dl in v0["deadlines"]:
            what = {"on_sale": f"Tickets on sale: {dl['name']}", "presale": f"Pre-sale lottery opens: {dl['name']}"}.get(
                dl["kind"], f"Book {dl['name']} (for {dl['for']})")
            when = dl.get("when", dl["date"]).replace("T", " ")
            H.append(f"<tr><td>{_e(when)}</td><td>{_e(what)}</td></tr>")
        H.append("</table>")
    H.append("<h2>Days</h2>")
    for v in v0["days"]:
        cls = "over" if budget and v["est_yen"] > budget else "under"
        H.append(f'<section class="day" id="d-{_e(v["date"])}">')
        hol = " · holiday" if v["holiday"] else ""
        H.append(f"<h3>{_e(v['weekday'].capitalize())} {_e(v['date'])} · {_e(v['city'] or '')}{hol}</h3>")
        if v.get("title"):
            H.append(f"<div><strong>{_e(v['title'])}</strong></div>")
        if v.get("stay"):
            st = v["stay"]
            ja = f" · <span class=\"ja\">{_e(st['name_ja'])}</span>" if st.get("name_ja") else ""
            addr = f"<br><span class=\"ja\">{_e(st['address_ja'])}</span>" if st.get("address_ja") else ""
            H.append(f'<div class="stay">🛏 {_e(st["name"])}{ja}{addr}</div>')
        H.append(_svg_map(v))
        H.append('<ol class="items">')
        for it in v["items"]:
            badges = "".join(
                f'<span class="badge {"partial" if c.get("partial") else "closed"}">'
                f'{_e(c.get("partial") or c["rule"])}</span>' for c in it.get("closed") or [])
            ja = f'<br><span class="ja">{_e(it["name_ja"])}</span>' if it.get("name_ja") else ""
            if it.get("address_ja"):
                ja += f' <span class="ja muted">{_e(it["address_ja"])}</span>'
            extra = []
            if it.get("hours"):
                extra.append(_e(it["hours"]))
            if it.get("tabelog_rating"):
                extra.append(f"Tabelog {_e(it['tabelog_rating'])}")
            if it.get("km_from_prev") is not None:
                extra.append(f"{it['km_from_prev']} km")
            if it.get("note"):
                extra.append(_e(it["note"]))
            H.append(f'<li><span class="cost">{_e(_yen(it.get("est_yen")))}</span><span class="slot">{_e(it.get("slot") or "")}</span>'
                     f'<a href="{_e(it["maps"])}">{_e(it["name"])}</a>{badges}{ja}'
                     + (f'<br><span class="muted">{" · ".join(extra)}</span>' if extra else "") + "</li>")
        H.append("</ol>")
        if v["events"]:
            H.append('<div class="muted">Events: ' + ", ".join(_e(e["name"]) for e in v["events"]) + "</div>")
        spent = f" · spent {_yen(v['spent_yen'])}" if v.get("spent_yen") is not None else ""
        H.append(f'<div>Estimated <span class="{cls}">{_e(_yen(v["est_yen"]))}</span>'
                 + (f" / budget {_e(_yen(budget))}" if budget else "") + f"{_e(spent)}</div>")
        body = day_bodies.get(v["id"], "")
        if body.strip():
            H.append(f'<div class="notes">{_body_html(body)}</div>')
        H.append("</section>")
    H.append("<script>(function(){var t=new Date(),p=function(n){return(n<10?'0':'')+n},"
             "id='d-'+t.getFullYear()+'-'+p(t.getMonth()+1)+'-'+p(t.getDate()),e=document.getElementById(id);"
             "if(e)e.scrollIntoView();})();</script>")
    H.append("</main></body></html>")
    return "\n".join(x for x in H if x != "") + "\n"
