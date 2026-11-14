---
id: <yyyy>-<slug>
type: trip
name: <Trip name>
country: <country-id>
start: YYYY-MM-DD
end: YYYY-MM-DD
status: planned       # planned | ongoing | done
stops:
  - from: YYYY-MM-DD
    to: YYYY-MM-DD
    place: <country>/<region>/<city>
    accommodation: <hotel-id>
    activities: [<activity-id>, ...]
    notes: ""
events: []            # ids of events overlapping the trip dates
days: []              # day-<YYYY-MM-DD> ids, one file per day in days/ (managed by scripts/sync.py)
rating: null          # 1-5 at the end
affinity: null
likes: []             # what we liked most about this trip
total_cost: null
---

# <Trip name>

## Summary

## Day-by-day itinerary

One file per day in `days/` (see `_templates/day.md`): `date`, `place`, `stay`, `area`, `plan:` (chosen activity/restaurant ids), `events`, `notes`. Query a day with `python3 scripts/query.py day --trip <trip-id> --date <YYYY-MM-DD>`.

## Expenses

## What we liked most / affinity

## For next time
