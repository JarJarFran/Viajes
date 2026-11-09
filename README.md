# Travels

Repository with **two separate but related knowledge domains**:

- **`destinations/`** — the knowledge graph of places: country → region → city → activity. Here we store objective, cumulative information about each place (what it is, how to get there, what can be done, prices, opening hours). It does not depend on when we go.
- **`trips/`** — our actual trips: dates, stops per day, what we did, where we slept, real expenses, ratings and affinity. Subjective, time-bound information.

The two domains connect only through **references between ids**: a trip points at `destinations/` nodes (`stops[].place`, `stops[].activities`), and `destinations/` nodes point back at trips (`trips`, `done_in`). Content is never mixed between the two.

Everything lives in plain Markdown with **YAML frontmatter**: readable by people, diff-friendly in git, and queryable by machines (the graph can be traversed with any script over the frontmatter).

## The two graphs and their edges

```
DESTINATIONS DOMAIN (knowledge of the place)        TRIPS DOMAIN (our experience)

country ──contains──▶ region ──contains──▶ city ──has──▶ activity
                                                               ▲
trip ──stops.place────────────────────────────▶ destination node ┘
trip ──stops.activities───────────────────────▶ activity record
     ◀── trips (backlink) ─── destination node
     ◀── done_in (backlink) ─── activity record
```

| | `destinations/` | `trips/` |
|---|---|---|
| What it stores | What exists in each place, objective data | What we did, subjective data |
| Examples | "Kyoto has Kinkaku-ji temple, entry 500 ¥" | "On 12/04/2025 we visited Kinkaku-ji, loved it, 5/5" |
| Changes over time | Rarely (hours, prices) | With every new trip |
| Typical fields | `id`, `path`, `contains`, `category`, `approx_cost` | `start`, `end`, `stops`, `total_cost`, `rating`, `affinity` |

## Node types and where they live

| Type | Folder | File |
|---|---|---|
| Country | `destinations/<country>/` | `README.md` |
| Region | `destinations/<country>/regions/<region>/` | `README.md` |
| City | `destinations/<country>/regions/<region>/cities/<city>/` | `README.md` |
| Activity | `.../cities/<city>/activities/<activity>.md` | single file |
| Restaurant | `.../cities/<city>/restaurants/<restaurant>.md` | single file |
| Trip | `trips/<trip-id>/` | `README.md` |
| Profile (our likes) | root | `profile.yaml` |
| Templates | `_templates/` | one per node type |

## Conventions

- **id**: unique, stable lowercase slug (`japan`, `kanto`, `tokyo`, `tokyo-sensoji`, `2025-japan`). Never reused.
- **path**: the node's route inside the destinations graph, e.g. `japan/kanto/tokyo`. It is independent of the physical folder and is used to link across domains.
- **Edges inside `destinations/`**:
  - Country → `contains: [regions]`; Region → `contains: [cities]` and `country: japan`; City → `region: kanto`.
  - Activity → `place: japan/kanto/tokyo`.
- **Edges across domains**:
  - Trip → `stops: [{ from, to, place: japan/kanto/tokyo, activities: [tokyo-sensoji], accommodation, notes }]` (a stop is a stay of one or more days at a destination node).
  - Backlinks: in the destination node `trips: [2025-japan]`; in the activity `done_in: [2025-japan]`.
- **Activity classification**: every activity has `entry: free | paid | mixed | n/a` (free sight vs paid entry vs free-to-enter-with-typical-spend vs transport) and optionally `area:` (neighborhood) to group a day by zone. Restaurants are their own node type (`restaurants/`) with `price_range: ¥–¥¥¥¥` and `area:` — separate from food *activities* (markets, street food, food tours).
- Example queries over the frontmatter: "all free activities in Kyoto" = activities with `place: japan/kansai/kyoto` and `entry: free`; "cheap eats in Tokyo" = restaurants with `place: japan/kanto/tokyo` and `price_range` of ¥ or ¥¥.
- **Affinity**: in `trips/`, each trip and its stops carry `affinity: 1-5` and `likes: [tags]` (our subjective rating). In `destinations/`, nodes may carry `affinity` as an accumulated summary from trips. Tags come from `profile.yaml`.
- The rating of an activity done on a trip is noted on the corresponding day of the trip; the activity record may keep a summary `rating`.
- All content in English; Japanese proper names keep their usual romanized form.

## How to add things

1. **Is it knowledge about a place?** → goes in `destinations/`, using a `_templates/` template (country, region, city or activity). Give it a new `id`, fill in the frontmatter, and update `contains`/`place` in the parent node.
2. **Is it something we did or are going to do?** → goes in `trips/<trip-id>/`, using `_templates/trip.md`. Each stop references `destinations/` nodes by their `path`/id, and when logging the stop, add the backlink (`trips` in the destination node, `done_in` in the activity).

## Open data sources (for researching destinations programmatically)

- [data.go.jp](https://www.data.go.jp/) — Japan national open data portal
- [MLIT multilingual sightseeing DB](https://www.mlit.go.jp/tagengo-db/en/index.html) — official sightseeing info by prefecture, in English
- [Tokyo Open Data](https://portal.data.metro.tokyo.lg.jp/) and [Tokyo Tourism Data Catalog](https://data.tourism.metro.tokyo.lg.jp/en/) — Tokyo Metropolitan Government datasets
- [Public Transportation Open Data Center (ODPT)](https://ckan.odpt.org/) — GTFS/GTFS-RT feeds for JR East, Tokyo Metro, Kyoto City Subway, etc.
- [e-Stat API](https://www.e-stat.go.jp/api/) — official statistics of Japan

## Index

- [profile.yaml](profile.yaml) — what we like (basis for affinity)
- [destinations/](destinations/) — knowledge graph of countries, regions, cities and activities
- [trips/](trips/) — trips done and planned, with days per place
- [_templates/](_templates/) — template for each node type
