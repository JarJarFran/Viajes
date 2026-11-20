---
id: <YYYY>-<slug>
type: trip
name: <Trip name>
country: <country-id>
start: YYYY-MM-DD          # arrival day
end: YYYY-MM-DD            # departure day
status: planned            # planned | ongoing | done | cancelled
stops:                     # contiguous: each stop's `to` (check-out) is the next stop's `from` (check-in)
  - {from: YYYY-MM-DD, to: YYYY-MM-DD, place: <country>/<region>/<city>, accommodation: <hotel-id>}
# days: [...]              # filled by scripts/sync.py, which also creates days/YYYY-MM-DD.md
---

# <Trip name>

## Summary

## Events in our window

<!-- gen:start events -->
<!-- gen:end events -->

## Budget

<!-- gen:start budget -->
<!-- gen:end budget -->

## Booking checklist

## What we liked most

<!-- gen:start liked -->
<!-- gen:end liked -->

## Days

<!-- gen:start days -->
<!-- gen:end days -->
