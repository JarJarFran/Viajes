"""Refresh the euro exchange rates used by the budget tables from the ECB daily reference rates.

    python3 scripts/update_fx.py            # update profile.yaml (budget.fx + budget.fx_date)
    python3 scripts/update_fx.py --dry-run  # only print the rates

`budget.fx` holds units of each currency per euro; every currency_code of a country node is refreshed.
"""
import argparse
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPO, load_graph, read, write  # noqa: E402

ECB = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"


def parse(xml, currencies):
    day = re.search(r"time=['\"](\d{4}-\d{2}-\d{2})['\"]", xml)
    rates = {c: float(m.group(1)) for c in currencies
             for m in [re.search(rf"currency=['\"]{c}['\"]\s+rate=['\"]([\d.]+)['\"]", xml)] if m}
    if not day or not rates:
        raise SystemExit("could not parse the ECB response")
    return day.group(1), rates


def fetch(currencies):
    req = urllib.request.Request(ECB, headers={"User-Agent": "travel-graph-fx/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return parse(r.read().decode("utf-8"), currencies)


def update_profile(text, day, rates):
    flow = "{" + ", ".join(f"{c}: {r}" for c, r in sorted(rates.items())) + "}"
    new = re.sub(r"(?m)^(\s*fx:\s*)\{[^}\n]*\}", lambda m: f"{m.group(1)}{flow}", text)
    return re.sub(r"(?m)^(\s*fx_date:\s*)\S+", lambda m: f"{m.group(1)}{day}", new)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    nodes, _, _ = load_graph(REPO)
    wanted = sorted({n["currency_code"] for n in nodes.values() if n.get("type") == "country" and n.get("currency_code")})
    day, rates = fetch(wanted or ["JPY"])
    print(f"ECB {day}: 1 EUR = " + ", ".join(f"{r} {c}" for c, r in sorted(rates.items())))
    if a.dry_run:
        return 0
    fp = os.path.join(REPO, "profile.yaml")
    text = read(fp)
    new = update_profile(text, day, rates)
    if new == text:
        print("profile.yaml already up to date (or has no budget.fx line)")
    else:
        write(fp, new)
        print("profile.yaml updated — run scripts/sync.py to refresh the budget tables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
