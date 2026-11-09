# Trips

Domain of **our experience**: each trip is a folder with a `README.md` whose frontmatter contains the **stops** (date → place → activities → accommodation), the real expenses, the final rating and the affinity.

Unlike `destinations/` (which stores the objective knowledge of each place), here we only store what happened to us on each trip.

## Relation with `destinations/`

- Each stop's `place` points to a node of the destinations graph (`japan/kanto/tokyo`), and each entry in `activities` to the id of a record in `destinations/.../activities/`.
- When logging a stop, add the backlink: the trip id in the `trips` field of the destination node and in `done_in` of each activity.

To create a new trip, copy [_templates/trip.md](../_templates/trip.md).

## Trip index

- [2025-japan](2025-japan/) — Japan: Osaka → Kyoto → Tokyo, 2025-12-26 → 2026-01-23 (planned)
