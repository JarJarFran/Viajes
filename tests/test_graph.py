"""Tests for the travel graph scripts. Each test builds a tiny repository in a temp dir.

    python3 -m unittest discover -s tests -v
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import fm as fmio  # noqa: E402
import exporters  # noqa: E402
import log as logcli  # noqa: E402
import sync  # noqa: E402
from common import ancestors, city_children, closures_on, load_graph, strict_restaurants  # noqa: E402
from validate_graph import validate  # noqa: E402

CITY = "destinations/japan/regions/kansai/cities"


class Fixture(unittest.TestCase):
    """Japan > Kansai > {Osaka, Kyoto}; trip Osaka (2 nights) -> Kyoto (1 night)."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        shutil.copy(os.path.join(REPO, "schema.yaml"), self.root)
        with open(os.path.join(self.root, "profile.yaml"), "w") as f:
            f.write("budget:\n  daily_eur_per_person: 100\n  eur_jpy: 160.0\n  eur_jpy_date: 2026-11-17\n")
        with open(os.path.join(self.root, "README.md"), "w") as f:
            f.write("# t\n\n<!-- gen:start catalog -->\n<!-- gen:end catalog -->\n")
        self.node("destinations/japan/README.md", id="japan", type="country", name="Japan",
                  holidays=[date(2027, 1, 11)])
        self.node("destinations/japan/regions/kansai/README.md", id="kansai", type="region", name="Kansai",
                  path="japan/kansai", country="japan")
        for c, ll in (("osaka", [34.69, 135.50]), ("kyoto", [35.01, 135.77])):
            self.node(f"{CITY}/{c}/README.md", id=c, type="city", name=c.capitalize(), path=f"japan/kansai/{c}",
                      country="japan", region="kansai", coords=ll,
                      body=f"\n# {c}\n\n## Restaurants\n\n<!-- gen:start restaurants -->\n<!-- gen:end restaurants -->\n")
        self.node(f"{CITY}/osaka/areas/osaka-area-namba.md", id="osaka-area-namba", type="area", name="Namba",
                  place="japan/kansai/osaka", coords=[34.669, 135.501])
        self.node(f"{CITY}/osaka/activities/osaka-castle.md", id="osaka-castle", type="activity", name="Osaka Castle",
                  place="japan/kansai/osaka", category="history", entry="paid", cost_yen=1200, tags=["top50"],
                  hours="9-17", closed=[{"yearly": "12-28..01-01"}], booking="walk-in", coords=[34.6873, 135.5262])
        self.node(f"{CITY}/osaka/activities/osaka-museum.md", id="osaka-museum", type="activity", name="Museum",
                  place="japan/kansai/osaka", category="museums", entry="paid", tags=[], hours="9-17",
                  closed=[{"weekly": ["mon"], "holiday_shift": True, "partial": "galleries"}], booking="required",
                  book_ahead_days=10, coords=[34.68, 135.52])
        self.node(f"{CITY}/osaka/restaurants/osaka-restaurant-a.md", id="osaka-restaurant-a", type="restaurant",
                  name="A", place="japan/kansai/osaka", area="osaka-area-namba", cuisine="ramen", price_range="¥¥¥¥",
                  budget_lunch_yen=[1000, 1999], budget_dinner_yen=[6000, 7999], tabelog_list="https://x/rstLst/",
                  tabelog_rating=3.6, coords=[34.67, 135.50])
        self.node(f"{CITY}/osaka/hotels/osaka-hotel-h.md", id="osaka-hotel-h", type="hotel", name="H",
                  place="japan/kansai/osaka", area="osaka-area-namba", price_range="¥¥¥", coords=[34.668, 135.502])
        self.node(f"{CITY}/kyoto/hotels/kyoto-hotel-k.md", id="kyoto-hotel-k", type="hotel", name="K",
                  place="japan/kansai/kyoto", price_range="¥¥¥", area="kyoto-area-st")
        self.node(f"{CITY}/kyoto/areas/kyoto-area-st.md", id="kyoto-area-st", type="area", name="Station",
                  place="japan/kansai/kyoto")
        self.node(f"{CITY}/kyoto/events/kyoto-fest.md", id="kyoto-fest", type="event", name="Fest",
                  place="japan/kansai/kyoto", entry="free",
                  editions=[{"start": date(2027, 1, 8), "end": date(2027, 1, 12),
                             "on_sale": datetime(2026, 12, 5, 10, 0, tzinfo=timezone(timedelta(hours=9)))}])
        self.node("destinations/japan/routes/osaka-to-kyoto.md", id="osaka-to-kyoto", type="route", name="O-K",
                  origin="japan/kansai/osaka", destination="japan/kansai/kyoto", mode="train", duration_hours=0.5,
                  approx_cost="¥580", price_yen=580)
        self.trip = dict(id="t1", type="trip", name="T", country="japan", start=date(2027, 1, 9),
                         end=date(2027, 1, 12), status="planned",
                         stops=[{"from": date(2027, 1, 9), "to": date(2027, 1, 11), "place": "japan/kansai/osaka",
                                 "accommodation": "osaka-hotel-h"},
                                {"from": date(2027, 1, 11), "to": date(2027, 1, 12), "place": "japan/kansai/kyoto",
                                 "accommodation": "kyoto-hotel-k"}])
        self.node("trips/t1/README.md", body="\n# T\n\n<!-- gen:start days -->\n<!-- gen:end days -->\n", **self.trip)
        self.run_sync()  # creates day files

    def tearDown(self):
        shutil.rmtree(self.root)

    def node(self, rel, body="\n# x\n", **fm):
        fp = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(fmio.render(fm, body))
        return fp

    def edit(self, rel, **changes):
        fp = os.path.join(self.root, rel)
        fm, body, err = fmio.parse(open(fp, encoding="utf-8").read())
        assert not err, err
        fm.update(changes)
        for k, v in list(fm.items()):
            if v is None:
                del fm[k]
        with open(fp, "w", encoding="utf-8") as f:
            f.write(fmio.render(fm, body))

    def run_sync(self, check=False):
        with redirect_stdout(io.StringIO()):
            return sync.run(self.root, check)

    def errors(self):
        errs, warns, _ = validate(self.root)
        return errs, warns


class TestValidation(Fixture):
    def test_fixture_is_consistent(self):
        errs, _ = self.errors()
        self.assertEqual(errs, [])

    def test_duplicate_id_is_reported(self):
        shutil.copy(os.path.join(self.root, CITY, "osaka/activities/osaka-castle.md"),
                    os.path.join(self.root, CITY, "osaka/activities/zz-copy.md"))
        errs, _ = self.errors()
        self.assertTrue(any("duplicate id 'osaka-castle'" in e for e in errs), errs)

    def test_broken_yaml_is_reported(self):
        with open(os.path.join(self.root, CITY, "osaka/activities/bad.md"), "w") as f:
            f.write("---\nid: bad\nname: [oops\n---\n")
        errs, _ = self.errors()
        self.assertTrue(any("bad.md: invalid YAML" in e for e in errs), errs)

    def test_unknown_key_is_reported(self):
        self.edit(f"{CITY}/osaka/activities/osaka-castle.md", colour="red")
        errs, _ = self.errors()
        self.assertTrue(any("unknown key 'colour'" in e for e in errs), errs)

    def test_stops_must_chain(self):
        stops = [dict(s) for s in self.trip["stops"]]
        stops[1]["from"] = date(2027, 1, 12)
        stops[1]["to"] = date(2027, 1, 12)
        self.edit("trips/t1/README.md", stops=stops)
        errs, _ = self.errors()
        self.assertTrue(any("stops must chain" in e for e in errs), errs)

    def test_day_place_and_stay_follow_checkout_semantics(self):
        fm, _, _ = fmio.parse(open(os.path.join(self.root, "trips/t1/days/2027-01-11.md")).read())
        self.assertEqual((fm["place"], fm.get("stay")), ("japan/kansai/kyoto", "kyoto-hotel-k"))
        last, _, _ = fmio.parse(open(os.path.join(self.root, "trips/t1/days/2027-01-12.md")).read())
        self.assertEqual(last["place"], "japan/kansai/kyoto")
        self.assertNotIn("stay", last)
        self.edit("trips/t1/days/2027-01-11.md", stay="osaka-hotel-h")
        errs, _ = self.errors()
        self.assertTrue(any("stay osaka-hotel-h should be kyoto-hotel-k" in e for e in errs), errs)

    def test_plan_in_wrong_city_is_reported(self):
        self.edit("trips/t1/days/2027-01-12.md", plan=[{"slot": "morning", "id": "osaka-castle"}])
        errs, _ = self.errors()
        self.assertTrue(any("osaka-castle is in" in e for e in errs), errs)
        # travel day: the city of the previous night is allowed
        self.edit("trips/t1/days/2027-01-12.md", plan=None)
        self.edit("trips/t1/days/2027-01-11.md", plan=[{"slot": "morning", "id": "osaka-castle"},
                                                        {"slot": "travel", "id": "osaka-to-kyoto"}])
        errs, _ = self.errors()
        self.assertEqual(errs, [])

    def test_partial_closure_is_a_warning(self):
        # Jan 11 2027 is a Monday holiday -> the museum (Mondays, holiday shift) closes Tuesday Jan 12 instead
        self.edit("trips/t1/days/2027-01-12.md", visits=["japan/kansai/osaka"],
                  plan=[{"slot": "morning", "id": "osaka-museum"}])
        errs, warns = self.errors()
        self.assertEqual(errs, [])
        self.assertTrue(any("osaka-museum on 2027-01-12" in w and "partial" in w for w in warns), warns)

    def test_closure_rules(self):
        hol = {date(2027, 1, 11)}
        museum = {"closed": [{"weekly": ["mon"], "holiday_shift": True}]}
        self.assertEqual(closures_on(museum, date(2027, 1, 11), hol), [])  # holiday Monday: open
        self.assertTrue(closures_on(museum, date(2027, 1, 12), hol))       # closed the next day
        self.assertTrue(closures_on(museum, date(2027, 1, 18), hol))       # ordinary Monday
        castle = {"closed": [{"yearly": "12-28..01-01"}]}
        self.assertTrue(closures_on(castle, date(2026, 12, 30)))
        self.assertTrue(closures_on(castle, date(2027, 1, 1)))
        self.assertFalse(closures_on(castle, date(2027, 1, 2)))
        nth = {"closed": [{"weekly": ["tue"], "nth": [1, 3]}]}
        self.assertTrue(closures_on(nth, date(2027, 1, 5)))    # 1st Tuesday
        self.assertFalse(closures_on(nth, date(2027, 1, 12)))  # 2nd Tuesday
        self.assertTrue(closures_on(nth, date(2027, 1, 19)))   # 3rd Tuesday

    def test_closure_conflict_detected(self):
        self.edit("trips/t1/days/2027-01-10.md", plan=[{"slot": "morning", "id": "osaka-castle"}])
        errs, _ = self.errors()
        self.assertEqual(errs, [])  # Jan 10 is open
        self.node(f"{CITY}/osaka/activities/osaka-zoo.md", id="osaka-zoo", type="activity", name="Zoo",
                  place="japan/kansai/osaka", category="leisure", entry="paid", tags=[], hours="9-17",
                  closed=[{"dates": "2027-01-10..2027-01-10"}], booking="walk-in")
        self.edit("trips/t1/days/2027-01-10.md", plan=[{"slot": "morning", "id": "osaka-zoo"}])
        errs, _ = self.errors()
        self.assertTrue(any("osaka-zoo on 2027-01-10" in e and "move it" in e for e in errs), errs)

    def test_event_outside_edition_is_reported(self):
        self.edit(f"{CITY}/kyoto/events/kyoto-fest.md", editions=[{"start": date(2027, 1, 11), "end": date(2027, 1, 12)}])
        self.edit("trips/t1/days/2027-01-10.md", visits=["japan/kansai/kyoto"], plan=[{"slot": "evening", "id": "kyoto-fest"}])
        errs, _ = self.errors()
        self.assertTrue(any("kyoto-fest is not on 2027-01-10" in e for e in errs), errs)

    def test_tabelog_list_page_must_not_be_in_tabelog(self):
        self.edit(f"{CITY}/osaka/restaurants/osaka-restaurant-a.md", tabelog="https://tabelog.com/en/osaka/rstLst/ramen/")
        errs, _ = self.errors()
        self.assertTrue(any("own page" in e for e in errs), errs)

    def test_broken_link_is_reported(self):
        with open(os.path.join(self.root, "trips/README.md"), "w") as f:
            f.write("[x](nowhere.md) [ok](t1/README.md) [web](https://example.com)\n")
        errs, _ = self.errors()
        self.assertEqual([e for e in errs if "broken link" in e], ["trips/README.md: broken link -> nowhere.md"])

    def test_wrong_folder_is_reported(self):
        src = os.path.join(self.root, CITY, "osaka/activities/osaka-castle.md")
        dst = os.path.join(self.root, CITY, "kyoto/activities/osaka-castle.md")
        os.makedirs(os.path.dirname(dst))
        shutil.move(src, dst)
        errs, _ = self.errors()
        self.assertTrue(any("should live at" in e for e in errs), errs)


class TestGraph(Fixture):
    def test_ancestors_have_no_duplicates(self):
        nodes, _, _ = load_graph(self.root)
        self.assertEqual(ancestors(nodes, "osaka"), ["kansai", "japan"])

    def test_city_children_exclude_trip_days(self):
        nodes, _, _ = load_graph(self.root)
        kids = city_children(nodes, "japan/kansai/osaka")
        self.assertIn("osaka-castle", kids)
        self.assertFalse(any(nodes[k]["type"] == "day" for k in kids))

    def test_stop_edges_keep_their_endpoints(self):
        nodes, paths, edges = load_graph(self.root)
        stops = [e for e in edges if e["rel"] == "stop"]
        self.assertEqual({(e["from"], e["to"]) for e in stops}, {("t1", "osaka"), ("t1", "kyoto")})
        self.assertEqual(stops[0]["check_in"][:4], "2027")

    def test_strict_filter_uses_cheapest_meal(self):
        nodes, _, _ = load_graph(self.root)
        self.assertEqual(strict_restaurants(nodes), ["osaka-restaurant-a"])  # lunch fits under ¥5,000

    def test_nearby_and_in_area_edges(self):
        nodes, paths, edges = load_graph(self.root)
        rels = {(e["from"], e["rel"], e["to"]) for e in edges}
        self.assertIn(("osaka-hotel-h", "nearby", "osaka-restaurant-a"), rels)
        self.assertNotIn(("osaka-castle", "in_area", "osaka-area-namba"), rels)  # 2.3 km away

    def test_done_creates_done_in_edge(self):
        with redirect_stdout(io.StringIO()):
            logcli.main(["done", "--trip", "t1", "--date", "2027-01-10", "--id", "osaka-castle", "--rating", "5"], self.root)
            logcli.main(["expense", "--trip", "t1", "--date", "2027-01-10", "--yen", "1200", "--what", "castle",
                         "--category", "sights"], self.root)
        nodes, _, edges = load_graph(self.root)
        self.assertIn({"from": "osaka-castle", "to": "t1", "rel": "done_in"}, edges)
        self.assertEqual(nodes["t1-2027-01-10"]["expenses"], [{"yen": 1200, "what": "castle", "category": "sights"}])
        errs, _ = self.errors()
        self.assertEqual(errs, [])


class TestSyncAndExports(Fixture):
    def test_sync_is_idempotent(self):
        self.assertEqual(self.run_sync(check=True), 0)
        self.edit(f"{CITY}/osaka/activities/osaka-castle.md", cost_yen=1500)
        self.assertEqual(self.run_sync(check=True), 1)
        self.run_sync()
        self.assertEqual(self.run_sync(check=True), 0)

    def test_trip_days_created_and_listed(self):
        nodes, _, _ = load_graph(self.root)
        self.assertEqual(nodes["t1"]["days"], [f"t1-2027-01-{x:02d}" for x in (9, 10, 11, 12)])

    def test_exports_are_valid(self):
        ex = os.path.join(self.root, "exports")
        for sub in ("index.json", "cities/osaka.json", "shortlists/osaka.json", "trips/t1.json"):
            with open(os.path.join(ex, sub), encoding="utf-8") as f:
                json.load(f)
        with open(os.path.join(ex, "maps/osaka.geojson"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["type"], "FeatureCollection")
        idx = json.load(open(os.path.join(ex, "index.json")))
        self.assertNotIn("t1-2027-01-10", json.load(open(os.path.join(ex, "cities/osaka.json")))["nodes"])
        self.assertIn("osaka-castle", idx["nodes"])

    def test_ics_is_folded_and_has_deadlines(self):
        raw = open(os.path.join(self.root, "exports/trips/t1.ics"), "rb").read()
        self.assertTrue(raw.endswith(b"\r\n"))
        for line in raw.split(b"\r\n"):
            self.assertLessEqual(len(line), 75)
        text = raw.decode("utf-8").replace("\r\n ", "")
        self.assertIn("DTSTART:20261205T010000Z", text)  # 10:00 JST
        self.assertEqual(text.count("BEGIN:VEVENT"), 4 + 1)  # 4 days + 1 sale

    def test_booking_reminder_uses_lead_days(self):
        self.edit("trips/t1/days/2027-01-10.md", plan=[{"slot": "morning", "id": "osaka-museum"}])
        self.run_sync()
        data = json.load(open(os.path.join(self.root, "exports/trips/t1.json")))
        book = [x for x in data["deadlines"] if x["kind"] == "book"]
        self.assertEqual(book, [{"kind": "book", "id": "osaka-museum", "name": "Museum", "date": "2026-12-31",
                                 "for": "2027-01-10", "booking": "required", "lead_days": 10}])

    def test_budget_estimate(self):
        self.edit("trips/t1/days/2027-01-10.md", plan=[{"slot": "morning", "id": "osaka-castle"},
                                                        {"slot": "lunch", "id": "osaka-restaurant-a"},
                                                        {"slot": "dinner", "id": "osaka-restaurant-a", "yen": 3000}])
        self.run_sync()
        data = json.load(open(os.path.join(self.root, "exports/trips/t1.json")))
        day = data["days"]["t1-2027-01-10"]
        self.assertEqual(day["est_yen"], 1200 + 1500 + 3000)
        self.assertEqual(day["budget_yen"], 16000)

    def test_html_page_is_self_contained(self):
        page = open(os.path.join(self.root, "exports/trips/t1.html"), encoding="utf-8").read()
        self.assertIn('id="d-2027-01-10"', page)
        self.assertNotIn("<script src", page)
        self.assertNotIn("<link", page)


class TestFrontmatter(unittest.TestCase):
    def test_roundtrip(self):
        fm = {"id": "x", "type": "activity", "hours": "9:00-17:00", "note": "a: b # c", "q": "it's \"quoted\"",
              "multi": "line1\nline2", "d": date(2027, 1, 2),
              "dt": datetime(2026, 12, 5, 10, 0, tzinfo=timezone(timedelta(hours=9))),
              "tags": ["a", "b"], "price": "¥¥", "empty": [], "n": None, "flag": "yes", "on": "off", "num": "0123",
              "stops": [{"from": date(2027, 1, 1), "to": date(2027, 1, 2), "place": "a/b",
                         "notes": "x" * 150}, {"from": date(2027, 1, 2), "to": date(2027, 1, 3), "place": "a/c"}],
              "closed": [{"weekly": ["mon"], "holiday_shift": True}, {"yearly": "12-28..01-04"}]}
        text = fmio.render(fm, "\n# body\n")
        back, body, err = fmio.parse(text)
        self.assertIsNone(err)
        self.assertEqual(back, fm)
        self.assertEqual(body, "\n# body\n")

    def test_no_frontmatter_and_unclosed(self):
        self.assertEqual(fmio.parse("# readme\n")[0], None)
        self.assertIsNotNone(fmio.parse("---\nid: x\n")[2])

    def test_json_records_is_valid_json(self):
        s = exporters.json_records({"a": 1, "nodes": {"x": {"k": 1}, "y": {"k": 2}}, "edges": [{"f": 1}, {"f": 2}]})
        self.assertEqual(json.loads(s), {"a": 1, "nodes": {"x": {"k": 1}, "y": {"k": 2}}, "edges": [{"f": 1}, {"f": 2}]})
        self.assertEqual(s.count("\n"), 11)  # one line per record


class TestRealRepo(unittest.TestCase):
    """Smoke tests on the committed data (read-only)."""

    def test_validator_passes(self):
        errs, _, _ = validate(REPO)
        self.assertEqual(errs, [])

    def test_query_commands_run(self):
        q = [sys.executable, os.path.join(REPO, "scripts", "query.py")]
        for args in (["stats"], ["restaurants", "--city", "osaka", "--area", "namba", "--max-yen", "1999", "--limit", "3"],
                     ["activities", "--city", "kyoto", "--open-on", "2027-01-01"], ["events", "--trip", "2026-japan"],
                     ["day", "--trip", "2026-japan", "--date", "2027-01-10"], ["budget", "--trip", "2026-japan"],
                     ["deadlines", "--trip", "2026-japan"], ["closures", "--trip", "2026-japan"],
                     ["near", "--id", "tokyo-sensoji", "--type", "restaurant"], ["stale", "--trip", "2026-japan"],
                     ["affinity"], ["routes", "--city", "kyoto"], ["areas", "--city", "tokyo"],
                     ["cluster", "--id", "kyoto-kiyomizu-dera"]):
            r = subprocess.run(q + args, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{args}: {r.stderr}")


if __name__ == "__main__":
    unittest.main()
