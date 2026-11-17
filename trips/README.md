# Trips

Domain of **our experience**: each trip is a folder with a `README.md` (the trip node) and one file per day in `days/`. Unlike `destinations/` (objective knowledge of each place), here we only store what we plan and what happened to us.

## How a trip is modelled

- **Stops** (`stops:` in the trip frontmatter) are contiguous stays: `from` = check-in day, `to` = check-out day. Each stop's `to` must equal the next stop's `from`, the first stop starts on the trip `start` and the last one ends on the trip `end` (departure day). The validator rejects gaps and overlaps, so every night has exactly one hotel.
- **Days** (`days/YYYY-MM-DD.md`, id `<trip>-<date>`) are created by `scripts/sync.py`. A day's `place`/`stay` are the city and hotel where we **sleep that night**; the departure day keeps the last city and has no stay.
- **Plan** items are `{slot, id}` (slot: early, morning, travel, day, lunch, afternoon, evening, dinner, night). They may reference the city of that night, the city of the previous night (travel days) and any city listed in `visits` (day trips: a `route` + nodes of the destination city). Add `yen:` to override the cost estimate (e.g. a round trip). Items keep the order you write; the computed day suggests a shorter order only when it saves ≥ 1 km.
- **After each day**, log what happened — ratings feed `query.py affinity`, expenses feed the budget tables:

  ```
  python3 scripts/log.py done    --trip 2026-japan --date 2027-01-10 --id tokyo-sumo-tournament --rating 5
  python3 scripts/log.py expense --trip 2026-japan --date 2027-01-10 --yen 3800 --what "sumo tickets" --category sights
  ```

Backlinks (`done_in`, events of a trip, events of a day) are derived in `exports/` — never written by hand.

To create a new trip, copy [_templates/trip.md](../_templates/trip.md) and run `python3 scripts/sync.py`.

## Trip index

- [2026-japan](2026-japan/) — Japan: Osaka → Kyoto → Tokyo, 2026-12-26 → 2027-01-23 (planned). Offline page: [exports/trips/2026-japan.html](../exports/trips/2026-japan.html) · calendar: [exports/trips/2026-japan.ics](../exports/trips/2026-japan.ics) · map: [exports/trips/2026-japan.geojson](../exports/trips/2026-japan.geojson)
