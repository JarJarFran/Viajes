# AGENTS.md — how an agent should read this repo (token budget matters)

This repository is a **travel knowledge graph consumed by agents/LLMs**, not a wiki. To answer "where should we eat / what should we see / what is optimal for this day", load the **smallest artifact that answers the question** — never walk all node files or full READMEs.

## Read order (cheapest first)

1. **`exports/shortlists/<city>.json`** — best options per city: top50/top100 sights (with area and closures), restaurants passing the strict filter (Tabelog ≥ 3.5 and some meal ≤ ¥4,999/person), events with editions, routes, areas.
2. **`exports/trips/<trip>.json`** — the computed trip: `summary` (nights, budget, totals), `deadlines` (ticket sales, booking reminders), `events` overlapping the trip, and `days.<day-id>` with the plan items in their planned order (slot, cost estimate, closures that day, coords, Google Maps link, km from the previous stop), `sunrise`/`sunset`, `warnings` (opening hours vs slot, meals far above the ¥4,999 cap, a shorter visiting order) and `suggestion`. Use it for anything about a trip.
3. **`exports/cities/<city>.json`** — every node of one city (plus routes touching it) and their edges.
4. **`exports/index.json`** — whole graph, one node/edge per line. Only for global questions.
5. **`python3 scripts/query.py <cmd> ...`** — filtered answers as JSON lines (default) or `--format md`:
   - `restaurants --city osaka --area namba --min-rating 3.5 --max-yen 1999 --meal lunch` · `restaurants --city tokyo --near tokyo-sensoji --km 0.8`
   - `near --id tokyo-sensoji --type restaurant --km 1` — anything around a node (needs coords)
   - `activities --city kyoto --entry free --tag top50 --open-on 2027-01-02` — drops places fully closed that day
   - `events --trip 2026-japan` / `events --on-date 2027-01-10` · `routes --city kyoto` · `areas --city tokyo` · `hotels --city tokyo`
   - `day --trip 2026-japan --date 2027-01-10` — the computed day (same as the trip export)
   - `budget --trip 2026-japan` · `deadlines --trip 2026-japan --upcoming` · `closures --trip 2026-japan` · `closures --id kyoto-nijo-castle --from 2026-12-25`
   - `stale --trip 2026-japan` — planned nodes never verified or verified ≥ 12 months ago
   - `affinity` — average ratings logged after trips, by category / cuisine / tag / city
   - `cluster --id kyoto-kiyomizu-dera` (curated `near` + derived proximity) · `node --id <id> [--body]` · `stats`

## Edges (in exports)

From scalar fields: `place`, `country`, `region`, `parent` (path), `area`, `near`, `origin`/`destination` (routes), trip `stop` (with check_in/check_out) / `stay` / `day`, day `trip` / `place` / `stay` / `visit` / `plan` (with slot) / `done` (with rating).
Derived: `event` (trip or day → events active then and there), `done_in` (node → trip, from logged `done`), `nearby` (sight/hotel/area → closest restaurants and sights within 1 km, with `km`), `in_area` (nodes without explicit area → nearest area centroid).

## Node files (source of truth — only when exports are not enough)

- Each `.md` node = **YAML frontmatter (data) + prose body**. Read the frontmatter; skip bodies unless asked for stories/tips.
- City READMEs contain generated lists — skip them, use `exports/`.
- `coords_precision: station` means the point is the restaurant's nearest station (see `station`, `station_m`), not the door.
- Restaurant `price_range` (bucket of the dinner budget, else generic, else lunch) and the `top-rated` tag (Tabelog ≥ 3.5) are derived by `sync.py`; `tabelog_rating` may be absent (chains, food halls).
- Day trips are a `route` plus nodes in the destination city, referenced from the day with `visits: [<city path>]` (e.g. Himeji, Nikko, Kawaguchiko, Kamakura).

## Schema & vocabularies

[schema.yaml](schema.yaml) lists every allowed key per type (unknown keys fail validation) and the vocabularies: `entry` free/paid/mixed/n/a · `booking` walk-in/reserve/required · `price_range` ¥…¥¥¥¥ · `category` · `slot` early/morning/travel/day/lunch/afternoon/evening/dinner/night · `tags` · `mode`. Closure rules (`closed:`) are documented in [_templates/activity.md](_templates/activity.md).

## Editing

```
python3 scripts/sync.py            # create day files, normalize nodes, rebuild generated blocks + exports/
python3 scripts/validate_graph.py  # must print "Graph consistent"; warnings never fail
python3 -m unittest discover -s tests
```

CI runs all three (`sync.py --check` instead of writing). Commit the regenerated `exports/`. Add coordinates with `python3 scripts/geocode.py` (OpenStreetMap, 1 request/second); log a trip day with `python3 scripts/log.py done|expense ...`; refresh the EUR/JPY rate with `python3 scripts/update_fx.py`.

## Domains

- `destinations/` — objective knowledge (no "we"/"our trip" prose; trip-specific notes go in day files).
- `trips/` — stops with check-in/check-out, `days/YYYY-MM-DD.md` with `plan`, `done`, `expenses`.
