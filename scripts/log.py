"""Log what actually happened on a trip day (writes the day file's frontmatter).

    python3 scripts/log.py done    --trip 2026-japan --date 2027-01-10 --id tokyo-sumo-tournament --rating 5 --note "makuuchi was amazing"
    python3 scripts/log.py expense --trip 2026-japan --date 2027-01-10 --yen 3800 --what "sumo tickets" --category sights
    python3 scripts/log.py show    --trip 2026-japan --date 2027-01-10

Ratings feed `query.py affinity` and the derived `done`/`done_in` edges; expenses feed the
budget tables (planned vs spent). Run scripts/sync.py afterwards to refresh exports.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fm as fmio  # noqa: E402
from common import REPO, SCHEMA, canonical, day_id, load_graph, write  # noqa: E402


def load_day(trip, date_, root=REPO):
    errors = []
    nodes, _, _ = load_graph(root, errors)
    if errors:
        sys.exit("fix the graph first: " + "; ".join(errors))
    did = day_id(trip, date_)
    if did not in nodes:
        sys.exit(f"no day {did} (run scripts/sync.py to create day files)")
    return nodes, nodes[did]


def save(day):
    write(day["_fp"], fmio.render(canonical(day), day["_body"]))


def main(argv=None, root=REPO):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("done", "expense", "show"):
        p = sub.add_parser(name)
        p.add_argument("--trip", required=True)
        p.add_argument("--date", required=True)
        if name == "done":
            p.add_argument("--id", required=True)
            p.add_argument("--rating", type=int, choices=[1, 2, 3, 4, 5])
            p.add_argument("--note")
        if name == "expense":
            p.add_argument("--yen", type=int, required=True)
            p.add_argument("--what", required=True)
            p.add_argument("--category", choices=SCHEMA["vocabularies"]["expense_category"])
    a = ap.parse_args(argv)
    nodes, day = load_day(a.trip, a.date, root)
    if a.cmd == "show":
        print(json.dumps({k: day.get(k) for k in ("id", "plan", "done", "expenses")}, ensure_ascii=False, indent=1,
                         default=str))
        return 0
    if a.cmd == "done":
        if a.id not in nodes:
            sys.exit(f"unknown id {a.id}")
        done = [x for x in day.get("done") or [] if x.get("id") != a.id]
        item = {"id": a.id}
        if a.rating is not None:
            item["rating"] = a.rating
        if a.note:
            item["note"] = a.note
        done.append(item)
        day["done"] = done
        msg = f"{day['id']}: done {a.id}" + (f" ({a.rating}/5)" if a.rating else "")
    else:
        if a.yen < 0:
            sys.exit("--yen must be >= 0")
        item = {"yen": a.yen, "what": a.what}
        if a.category:
            item["category"] = a.category
        day["expenses"] = list(day.get("expenses") or []) + [item]
        total = sum(x.get("yen", 0) for x in day["expenses"])
        msg = f"{day['id']}: expense ¥{a.yen:,} ({a.what}); day total ¥{total:,}"
    save(day)
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
