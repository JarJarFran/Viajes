---
# Day files are created by scripts/sync.py from the trip window; place/stay are checked by the validator.
id: <trip-id>-<YYYY-MM-DD>
type: day
date: <YYYY-MM-DD>
trip: <trip-id>
place: <country>/<region>/<city>   # city where we sleep that night (last day: departure city)
stay: <hotel-id>                   # accommodation of the stop covering that night
title: <short title of the day>
visits: []                         # day-trip cities whose nodes may appear in plan
plan:
  - {slot: morning, id: <activity-id>}
  - {slot: lunch, id: <restaurant-id>}
  - {slot: travel, id: <route-id>, cost: 2040, note: round trip}   # cost (local currency) overrides the estimate
done: []        # after the day: python3 scripts/log.py done --trip ... --date ... --id ... --rating 1-5
expenses: []    # python3 scripts/log.py expense --trip ... --date ... --amount ... --what ...
---

# <YYYY-MM-DD> — <city>

**<title>**

## Itinerary

## Events today

<!-- gen:start events -->
<!-- gen:end events -->

## Notes
