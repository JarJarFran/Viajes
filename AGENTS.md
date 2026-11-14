# AGENTS.md — how an agent should read this repo (token budget matters)

This repository is a **travel knowledge graph consumed by agents/LLMs**, not a wiki. Your job when answering "where should we eat / what should we see / what is optimal for this day" is to load the **smallest artifact that answers the question** — never walk all node files or full READMEs.

## Read order (cheapest first)

1. **`exports/shortlists/<city>.json`** — the "best options" per city: top50/top100 activities + restaurants passing the strict filter (Tabelog ≥ 3.5 and < ¥5,000/person) + events. Use this for "what are our best options in X?".
2. **`exports/cities/<city>.json`** — one city only: all its nodes (activities, events, restaurants, hotels) + edges. Use when the shortlist is not enough.
3. **`exports/trips/<trip>.json`** — a trip with its day nodes (`days/`), stops, stays, events and related node summaries. Use for anything about a specific trip.
4. **`exports/index.json`** — the whole graph (nodes + typed edges). Only load if you really need global queries.
5. **`python3 scripts/query.py <cmd> ...`** — filtered queries, prints compact JSON lines (default) or `--format md` tables:
   - `query.py plan --city tokyo --area shibuya --min-rating 3.5 --max-yen 4999 --with-activities` — candidate restaurants (and top sights) for a day
   - `query.py restaurants --city osaka --area namba --min-rating 3.5 --max-yen 4999 --sort rating`
   - `query.py activities --city kyoto --entry free --tag top50`
   - `query.py events --trip 2026-japan` / `events --on-date 2027-01-10`
   - `query.py day --trip 2026-japan --date 2027-01-10` — one day's plan + events (with detail)
   - `query.py cluster --id tokyo-sensoji` — walking cluster via `near`
   - `query.py node --id <id>` — one node's frontmatter (`--body` adds prose)
   - `query.py stats`

## Node files (source of truth, only when exports are missing)

- Each `.md` node = **YAML frontmatter (the data) + optional prose body**. Read the frontmatter; **do not read bodies** unless the user asks for stories/details — bodies are human prose.
- READMEs of cities/regions contain generated link lists — skip them, use `exports/`.
- Edges are derived from scalar fields (`place`, `country`, `region`, `path`, `near`, `done_in`, trip `stops`/`days`/`events`, day `plan`/`stay`/`events`) and materialized in `exports/index.json`.

## Schema & vocabularies

`schema.yaml` defines node types, required keys and enums (`entry`: free/paid/mixed/n/a · `booking`: walk-in/reserve/required · `price_range`: ¥/¥¥/¥¥¥/¥¥¥¥ · `tags`: top50, top100, touristic, iconic, unesco, hidden-gem, night, event, kid-friendly, top-rated). `scripts/validate_graph.py` enforces schema + reference integrity.

## Editing

To add/change a node: copy `_templates/<type>.md`, fill frontmatter, then run:

```
python3 scripts/sync.py            # normalize nodes, rebuild exports/, create trip day files
python3 scripts/validate_graph.py  # must print "Graph consistent"
```

CI runs both (plus `sync.py --check`) on every PR. `scripts/sync.py` is what keeps `exports/` in sync — commit its output.

## Domains

- `destinations/` — objective knowledge: country → region → city → activities/events/restaurants/hotels.
- `trips/` — our experience: trip node + `days/YYYY-MM-DD.md` per day (place, stay, `plan:` chosen ids, events, notes). Linked only by id references.
