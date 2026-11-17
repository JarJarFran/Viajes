"""Refresh the EUR/JPY rate used by the budget tables from the ECB daily reference rates.

    python3 scripts/update_fx.py            # update profile.yaml (budget.eur_jpy / eur_jpy_date)
    python3 scripts/update_fx.py --dry-run  # only print the rate
"""
import argparse
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPO, read, write  # noqa: E402

ECB = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"


def fetch():
    req = urllib.request.Request(ECB, headers={"User-Agent": "travel-graph-fx/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        xml = r.read().decode("utf-8")
    day = re.search(r"time=['\"](\d{4}-\d{2}-\d{2})['\"]", xml)
    jpy = re.search(r"currency=['\"]JPY['\"]\s+rate=['\"]([\d.]+)['\"]", xml)
    if not day or not jpy:
        raise SystemExit("could not parse the ECB response")
    return day.group(1), float(jpy.group(1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    day, rate = fetch()
    print(f"ECB {day}: 1 EUR = {rate} JPY")
    if a.dry_run:
        return 0
    fp = os.path.join(REPO, "profile.yaml")
    text = read(fp)
    new = re.sub(r"(?m)^(\s*eur_jpy:\s*)[\d.]+", lambda m: f"{m.group(1)}{rate}", text)
    new = re.sub(r"(?m)^(\s*eur_jpy_date:\s*)\S+", lambda m: f"{m.group(1)}{day}", new)
    if new == text:
        print("profile.yaml already up to date (or has no budget block)")
    else:
        write(fp, new)
        print("profile.yaml updated — run scripts/sync.py to refresh the budget tables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
