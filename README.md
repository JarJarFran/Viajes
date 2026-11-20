# Travels

A travel knowledge graph in plain Markdown + YAML frontmatter, with **two separate domains**:

- **`destinations/`** — objective, cumulative knowledge of places: country → region → city → areas, activities, events, restaurants, hotels, plus routes between cities. It does not depend on when we go.
- **`trips/`** — our trips: stops (where we sleep), one file per day with the plan, and afterwards what we did, ratings and real expenses.

The domains connect only through **id references** (a day's `plan` points at destination ids); every backlink (`done_in`, events during a trip, sights near a restaurant…) is **derived** into `exports/`, never written by hand. The repo is **agent-first**: frontmatter is the data, bodies are human prose, and the committed `exports/` plus `scripts/query.py` are the cheap read path — see [AGENTS.md](AGENTS.md).

## Quick start

```
pip install -r requirements.txt
python3 scripts/sync.py              # create day files, normalize nodes, rebuild generated blocks and exports/
python3 scripts/validate_graph.py    # must print "Graph consistent" (CI also runs sync --check and the tests)
python3 -m unittest discover -s tests

python3 scripts/query.py day --trip 2026-japan --date 2027-01-10      # one day: plan, costs, closures, events
python3 scripts/query.py near --id tokyo-sensoji --type restaurant     # where to eat around a sight
python3 scripts/query.py deadlines --trip 2026-japan --upcoming        # ticket sales and booking reminders
```

**For the trip itself:** import [exports/trips/2026-japan.ics](exports/trips/2026-japan.ics) into the phone calendar (one event per day + ticket-sale alarms + booking reminders) and save [exports/trips/2026-japan.html](exports/trips/2026-japan.html) on the phone — a self-contained page that works offline, with local-script names/addresses for taxis, a schematic map per day and the cost of each day. GitHub renders [exports/maps/](exports/maps/) and [exports/trips/2026-japan.geojson](exports/trips/2026-japan.geojson) as interactive maps.

## Node types

| Type | Lives in | Key fields |
|---|---|---|
| country | `destinations/<country>/README.md` | `holidays` (used by closure rules) |
| region | `destinations/<country>/regions/<region>/README.md` | `path`, `country` |
| city | `.../regions/<region>/cities/<city>/README.md` | `path`, `country`, `region`, `coords` |
| area | `.../cities/<city>/areas/<id>.md` | neighbourhood centroid + `aliases` |
| activity | `.../cities/<city>/activities/<id>.md` | `category`, `entry`, `cost`, `hours`, `closed` rules, `booking` |
| event | `.../cities/<city>/events/<id>.md` | `recurrence` + `editions: [{start, end, on_sale}]` |
| restaurant | `.../cities/<city>/restaurants/<id>.md` | `area`, `budget_lunch`/`budget_dinner`, `tabelog_rating` (Japan) or `guide` (elsewhere), `station` |
| hotel | `.../cities/<city>/hotels/<id>.md` | `area`, `price_range` |
| route | `destinations/<country>/routes/<id>.md` | `origin`, `destination`, `mode`, `price` |
| trip | `trips/<trip>/README.md` | `stops` (check-in/check-out, contiguous) |
| day | `trips/<trip>/days/YYYY-MM-DD.md` | `place`, `stay`, `plan: [{slot, id}]`, `done`, `expenses` |

Templates for every type are in [_templates/](_templates/); [schema.yaml](schema.yaml) lists every allowed key (unknown keys are errors) and the vocabularies.

## Conventions

- **ids** are stable lowercase slugs (`tokyo-sensoji`, `kyoto-area-gion`, `2026-japan-2027-01-10`); **paths** (`japan/kanto/tokyo`) identify cities for `place`, `origin`, `destination`, `visits`.
- **Stops**: `from` = check-in, `to` = check-out; consecutive stops must chain so every night has exactly one hotel. A day's `place`/`stay` = where we sleep that night.
- **Plans**: a day may use nodes of that night's city, the previous night's city (travel days) and its `visits` (day trips). The validator checks cities, event dates and closures (`closed` rules with weekly / nth-weekday / yearly / one-off dates and public-holiday shifts; `partial` closures are warnings).
- **Day trips** = a `route` + nodes of the destination city; the day lists the city in `visits` and the round-trip fare as `cost` on the route item.
- **Derived fields**: `sync.py` sets restaurant `price_range` from the budgets (dinner, else generic, else lunch) and the `top-rated` tag from `tabelog_rating ≥ 3.5`.
- **Plan warnings** (never fail CI): opening hours that do not fit the slot, meals whose Tabelog budget for that slot is above ¥4,999, a visiting order that is ≥ 1 km and 15 % shorter, `near` links over 2 km, places far from their area. Each day also shows sunrise/sunset.
- **Local transport**: each city's `local_transport_day` (Tokyo ¥1,000, Kyoto ¥1,100, Osaka ~¥800) is added to every day planned there; city READMEs compare the passes.
- **Hotels** carry `check_in` / `check_out` times and the Japanese address; the day view shows check-out/check-in on moving days and the offline page has a taxi card per hotel plus emergency numbers (`emergency` on the country node).
- **Money**: `cost` / `price` / restaurant budgets / expense `amount` are per person **in the currency of the node's country** (`currency_code` on the country node: JPY, CNY). Price buckets (`¥`…`¥¥¥¥`) and the strict cap are defined per currency in [schema.yaml](schema.yaml). Day estimates are compared with `budget.daily_eur_per_person` × the ECB rate of that currency (`budget.fx` in [profile.yaml](profile.yaml); `scripts/update_fx.py` refreshes every country's currency). Hotels are not counted.
- **Freshness**: `verified: YYYY-MM` records when hours/prices were last checked; `query.py stale --trip <id>` lists what to re-check before travelling.
- **Coordinates** come from OpenStreetMap via `scripts/geocode.py` with a `coords_precision` (`exact`, `station` = restaurant's nearest station, `area`). Data © OpenStreetMap contributors (ODbL).
- Content in English; names and addresses in the local script in `name_local` / `address_local` (Japanese, Chinese).

## Architecture

```
SOURCE OF TRUTH (hand-edited Markdown, frontmatter = data)
  destinations/…  trips/<trip>/README.md  trips/<trip>/days/*.md  profile.yaml  schema.yaml
        │  scripts/sync.py — creates day files, normalizes frontmatter, fills <!-- gen:start X --> blocks
        ▼
EXPORTS (committed; CI fails if stale) — one record per line, so diffs stay readable
  exports/index.json              whole graph: nodes + typed edges (incl. derived nearby / in_area / done_in)
  exports/cities/<city>.json      one city: its nodes, routes and edges
  exports/shortlists/<city>.json  best options: top sights, strict restaurants, events, routes, areas
  exports/maps/<city>.geojson     map of the city (GitHub renders it)
  exports/trips/<trip>.json       computed trip: per-day items, cost estimates, closures, events, deadlines
  exports/trips/<trip>.ics        calendar: days, ticket sales (with alarms), booking reminders
  exports/trips/<trip>.html       offline page for the phone
  exports/trips/<trip>.geojson    route of every day on a map
        │  scripts/validate_graph.py — schema, references, file locations, trip/day rules, closures, links
        ▼
QUERIES  scripts/query.py   ·   LOGGING  scripts/log.py   ·   DATA  scripts/geocode.py, scripts/update_fx.py
```

## How to add things

1. **Knowledge about a place** → copy the right `_templates/<type>.md` into `destinations/`, fill the frontmatter (`place: <country>/<region>/<city>`), run `python3 scripts/geocode.py` for coordinates.
2. **A trip** → copy `_templates/trip.md` into `trips/<id>/README.md` with its stops, run `scripts/sync.py` (it creates the day files), then fill each day's `plan`.
3. Run `python3 scripts/sync.py && python3 scripts/validate_graph.py` and commit everything, exports included.

## Open data sources

- [data.go.jp](https://www.data.go.jp/) — Japan national open data portal
- [MLIT multilingual sightseeing DB](https://www.mlit.go.jp/tagengo-db/en/index.html) — official sightseeing info by prefecture, in English
- [Tokyo Open Data](https://portal.data.metro.tokyo.lg.jp/) and [Tokyo Tourism Data Catalog](https://data.tourism.metro.tokyo.lg.jp/en/) — Tokyo Metropolitan Government datasets
- [Public Transportation Open Data Center (ODPT)](https://ckan.odpt.org/) — GTFS/GTFS-RT feeds for JR East, Tokyo Metro, Kyoto City Subway, etc.
- [e-Stat API](https://www.e-stat.go.jp/api/) — official statistics of Japan
- [OpenStreetMap Nominatim](https://nominatim.org/) — geocoding used by `scripts/geocode.py` (max 1 request/second)
- [ECB euro reference rates](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html) — EUR/JPY for budgets
- **Tabelog (restaurant data)**: no official API. Use [tabelog.com/en](https://tabelog.com/en/) manually (score 0–5, 3.5+ = excellent). Put the restaurant's own page in `tabelog:`; when the score was read on a list page, keep that URL in `tabelog_list:` (most current nodes — the validator reports how many still lack their own page). Tabelog's ToS disallow mass scraping.

## Index

- [AGENTS.md](AGENTS.md) — how agents should read/query this repo
- [schema.yaml](schema.yaml) · [profile.yaml](profile.yaml) · [_templates/](_templates/)
- [destinations/](destinations/) · [trips/](trips/) · [exports/](exports/) · [scripts/](scripts/) · [tests/](tests/)

<!-- gen:start catalog -->
## Catalog size (generated by `scripts/sync.py` — do not edit by hand)

- Nodes: 684 (153 activity, 36 area, 37 city, 1 country, 29 day, 20 event, 9 hotel, 8 region, 372 restaurant, 18 route, 1 trip); edges: 2755
- Restaurants per city (total / Tabelog >= 3.5 with a meal <= ¥4,999/person): kyoto: 110/51, osaka: 130/60, tokyo: 132/72
- Geolocated places: 586/590 (OpenStreetMap)
<!-- gen:end catalog -->
