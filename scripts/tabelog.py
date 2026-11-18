"""Refresh restaurant nodes from their own Tabelog page (English site): rating, address,
structured opening hours, closing-day rules and year-end/New Year notices.

    python3 scripts/tabelog.py --trip 2026-japan      # restaurants planned in a trip (need `tabelog:`)
    python3 scripts/tabelog.py --ids a,b --dry-run     # print what would change
    python3 scripts/tabelog.py --show <tabelog url>    # parse one page and print it

Only pages already linked in `tabelog:` are read (no crawling), one request every 3 s, cached
in scripts/.tabelog-cache/. Tabelog's terms do not allow mass scraping: keep it to the handful of
restaurants you actually plan to visit. Requires network access to tabelog.com.
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm as fmio  # noqa: E402
from common import REPO, canonical, load_graph, plan_items, write  # noqa: E402

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tabelog-cache")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
DAYS = {"mon": "mon", "tue": "tue", "wed": "wed", "thu": "thu", "fri": "fri", "sat": "sat", "sun": "sun",
        "public holiday": "hol", "day before public holiday": "pre_hol", "day after public holiday": "post_hol"}
FULL = {"monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu", "friday": "fri",
        "saturday": "sat", "sunday": "sun"}
WEEKDAY_RE = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"
ORDS = r"(?:first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th)"
ORD_N = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5}
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}
_last = [0.0]


def fetch(url, use_cache=True):
    os.makedirs(CACHE, exist_ok=True)
    fp = os.path.join(CACHE, re.sub(r"[^A-Za-z0-9]+", "_", url)[-150:] + ".html")
    if use_cache and os.path.exists(fp) and time.time() - os.path.getmtime(fp) < 7 * 86400:
        return open(fp, encoding="utf-8").read()
    wait = 3.0 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8", "replace")
    _last[0] = time.time()
    with open(fp, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def _text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _t24(h, m, ampm):
    h, m = int(h), int(m)
    if ampm == "AM":
        h = 0 if h == 12 else h
    elif ampm == "PM" and h != 12:
        h += 12
    return h * 60 + m


def parse_times(s):
    """'11:00 AM - 9:30 PM L.O. 9:00 PM' -> '11:00-21:30'; 'Open 24 hours' -> '00:00-24:00'."""
    if "24 hours" in s:
        return "00:00-24:00"
    m = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)?\s*-\s*(\d{1,2}):(\d{2})\s*(AM|PM)?", s)
    if not m:
        return None
    a = _t24(m.group(1), m.group(2), m.group(3))
    b = _t24(m.group(4), m.group(5), m.group(6))
    if b == 0:
        b = 24 * 60
    return f"{a // 60:02d}:{a % 60:02d}-{b // 60:02d}:{b % 60:02d}"


def parse_page(t, url=""):
    """Structured data from an English Tabelog restaurant page."""
    rows = {_text(th): td for th, td in re.findall(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", t, re.S)}
    m = re.search(r"rdheader-rating__score-val-dtl[^>]*>([\d.]+)", t)
    hdr = re.search(r"closed-label[^>]*>.*?</(?:span|p|dt)>(.*?)</(?:span|p|dd)>", t, re.S)
    name = re.search(r'<h2 class="display-name">\s*<span[^>]*>(.*?)</span>', t, re.S)
    bh = rows.get("Business hours", "")
    hours = []
    for it in re.findall(r'<li class="rstinfo-table__business-item">(.*?)</ul>\s*</li>', bh, re.S):
        tt = re.search(r'business-title">(.*?)</p>', it, re.S)
        hours.append({"days": _text(tt.group(1)) if tt else "",
                      "times": [_text(x) for x in re.findall(r'business-dtl-text">(.*?)</li>', it, re.S)]})
    note = " ".join(_text(x) for x in re.findall(r'rstinfo-table__business-other[^>]*>(.*?)</(?:p|div)>', bh, re.S))
    address = _text(rows.get("Address", "")).replace("Show larger map", "").replace("Find nearby restaurants", "")
    return {"url": url, "name": _text(name.group(1)) if name else "",
            "rating": float(m.group(1)) if m else None,
            "closed_header": _text(hdr.group(1)).lstrip("：: ") if hdr else "",
            "hours": hours, "note": note, "address": address.strip(),
            "reservation": _text(rows.get("Reservation availability", ""))}


def to_fields(p):
    """Node fields from a parsed page: opening, closed, hours (text), address_ja, booking hints."""
    opening, closed_days = [], []
    for h in p["hours"]:
        days = [DAYS.get(x.strip().lower()) for x in h["days"].split(",")]
        days = [x for x in days if x]
        times = [x for x in (parse_times(t) for t in h["times"]) if x]
        if any(t.strip().lower() == "closed" for t in h["times"]):
            closed_days += days
        elif days and times:
            opening.append({"days": days, "times": times})
    for w in re.split(r"[,、]", p["closed_header"] or ""):
        k = FULL.get(w.strip().lower())
        if k and k not in closed_days:
            closed_days.append(k)
        if w.strip().lower() == "public holiday" and "hol" not in closed_days:
            closed_days.append("hol")
    note = (p["note"] or "").replace("　", " ")
    low = note.lower()
    rules = []
    # the "closed on" part of the notes: Tabelog writes "■Closed on ..." up to the next "■"
    seg = " ".join(re.findall(r"closed on([^■]*)", low))
    nth_rules = []
    lists = rf"((?:{ORDS}(?:\s*,\s*and\s+|\s*,\s*|\s+and\s+)?)+)\s+({WEEKDAY_RE})s?"
    for m in re.finditer(lists, seg):
        ns = sorted({ORD_N[x] for x in re.findall(ORDS, m.group(1))})
        nth_rules.append({"weekly": [FULL[m.group(2)]], "nth": ns})
    plain = re.sub(lists, " ", seg)
    # conditional holiday shifts ("the following Tuesday if Monday is a public holiday") are not closing days
    plain = re.sub(rf"(?:the )?following (?:day|{WEEKDAY_RE})|if (?:{WEEKDAY_RE}|it) (?:is|falls on) a public holiday",
                   " ", plain)
    for w in re.findall(rf"\b({WEEKDAY_RE})s?\b", plain):
        if FULL[w] not in closed_days:
            closed_days.append(FULL[w])
    weekly = [x for x in closed_days if x in FULL.values()]
    if weekly:
        rule = {"weekly": sorted(weekly, key=list(FULL.values()).index)}
        if re.search(r"following (?:day|tuesday|wednesday|thursday|friday)[^.]*public holiday|"
                     r"public holiday[^.]*following day|falls on a public holiday", low):
            rule["holiday_shift"] = True
        rules.append(rule)
    if "hol" in closed_days:
        rules.append({"holidays": True})
    rules += nth_rules
    m = re.search(r"(december)\s+(\d{1,2})\s+(?:to|until|-|–)\s+(january)\s+(\d{1,2})", low)
    if m:
        rules.append({"yearly": f"12-{int(m.group(2)):02d}..01-{int(m.group(4)):02d}"})
    else:
        m = re.search(r"closed on (january|december) (\d{1,2})", low)
        if m:
            md = f"{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
            rules.append({"yearly": f"{md}..{md}"})
        elif re.search(r"year-end|new year", low) and "open year-round" not in low.split("(")[0]:
            rules.append({"yearly": "12-29..01-03", "maybe": "year-end & New Year holidays (dates not published)"})
        elif re.search(r"\(with year-end", low):
            rules.append({"yearly": "12-29..01-03", "maybe": "year-end & New Year holidays (dates not published)"})
    if re.search(r"not fixed|irregular|may close unexpectedly|temporary closures", low):
        rules.append({"irregular": "irregular closing days — check the restaurant's social media"})
    text = "; ".join(f"{','.join(o['days'])} {' & '.join(o['times'])}" for o in opening)
    out = {"opening": opening, "closed": rules, "hours": text or None, "address_ja": p["address"] or None}
    if re.search(r"(?:dinner|lunch|all seats)[^.■]*by reservation only|reservations? (?:are )?required", low):
        out["booking"] = "required"
    return out


def apply(n, p, today=None):
    f = to_fields(p)
    for k in ("opening", "hours", "address_ja"):
        if f.get(k):
            n[k] = f[k]
    n["closed"] = f["closed"]
    if f.get("booking"):
        n["booking"] = f["booking"]
    if p.get("rating") is not None:
        n["tabelog_rating"] = p["rating"]
    n["tabelog"] = p["url"]
    n["verified"] = (today or date.today()).isoformat()
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trip")
    ap.add_argument("--ids")
    ap.add_argument("--show")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    if a.show:
        p = parse_page(fetch(a.show, not a.no_cache), a.show)
        print(json.dumps({"page": p, "fields": to_fields(p)}, ensure_ascii=False, indent=1))
        return 0
    nodes, _, _ = load_graph(REPO)
    ids = set(a.ids.split(",")) if a.ids else set()
    if a.trip:
        for day in (n for n in nodes.values() if n.get("type") == "day" and n.get("trip") == a.trip):
            ids |= {i["id"] for i in plan_items(day) if nodes.get(i["id"], {}).get("type") == "restaurant"}
    if not ids:
        ap.error("give --trip or --ids")
    for rid in sorted(ids):
        n = nodes[rid]
        if not n.get("tabelog"):
            print(f"{rid}: no own `tabelog:` page — find it on tabelog.com/en and add it")
            continue
        p = parse_page(fetch(n["tabelog"], not a.no_cache), n["tabelog"])
        before = {k: n.get(k) for k in ("opening", "closed", "tabelog_rating", "booking")}
        apply(n, p)
        changed = [k for k in before if before[k] != n.get(k)]
        print(f"{rid}: {p['name']} {p['rating']} — " + (", ".join(changed) + " updated" if changed else "no change"))
        if not a.dry_run:
            write(n["_fp"], fmio.render(canonical(n), n["_body"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
