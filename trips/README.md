# Trips

Domain of **our experience**: each trip is a folder with a `README.md` whose frontmatter contains the **stops** (date → place → activities → accommodation), the real expenses, the final rating and the affinity.

Unlike `destinations/` (which stores the objective knowledge of each place), here we only store what happened to us on each trip.

## Relation with `destinations/`

- Each stop's `place` points to a node of the destinations graph (`japan/kanto/tokyo`), and each entry in `activities` to the id of a record in `destinations/.../activities/`.
- When logging a stop, add the backlink: the trip id in the `trips` field of the destination node and in `done_in` of each activity.

To create a new trip, copy [_templates/trip.md](../_templates/trip.md).

## Trip index

- [2026-japan](2026-japan/) — Japan: Osaka → Kyoto → Tokyo, 2026-12-26 → 2027-01-23 (planned); one file per day in [days/](2026-japan/days/) (`plan:` holds the chosen activity/restaurant ids — query with `python3 scripts/query.py day --trip 2026-japan --date YYYY-MM-DD`)
