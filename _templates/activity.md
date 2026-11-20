---
id: <city>-<activity-slug>
type: activity
name: <Activity name>
place: <country>/<region>/<city>
area: <city>-area-<slug>   # optional; otherwise derived from coords (exports in_area edge)
category: <temple | history | museums | nature | hiking | onsen | food | leisure | daytrip | other>
duration_hours: 2
approx_cost: "¥500"        # human text
cost: 500                  # per person in the country's currency, used by budgets (0 = free); omit if unknown
entry: <free | paid | mixed | n/a>
tags: []                   # top50, top100, touristic, iconic, unesco, hidden-gem, night, event, kid-friendly, rainy-day
hours: "9:00-17:00"
closed: []                 # rules, see below; [] = no known closures
# closed:
#   - {weekly: [mon], holiday_shift: true}      # closed Mondays; if Monday is a holiday, closed Tuesday
#   - {weekly: [tue], nth: [1, 3]}               # 1st and 3rd Tuesday of the month
#   - {yearly: 12-29..01-03}                     # every year (may wrap the new year)
#   - {dates: 2027-01-10..2027-01-24}            # one-off
#   - {specific: [2027-01-15, 2027-02-03]}       # single days
#   - {yearly: 01-01..01-03, partial: "palace only; grounds open"}   # warning instead of error
#   - {irregular: "maintenance days in January"} # informative only
booking: walk-in           # walk-in | reserve | required
book_ahead_days: 14        # optional: calendar reminder lead time (default 30 for required, 7 for reserve)
near: []                   # optional curated walking cluster (proximity is also derived from coords)
best_season: all year round
best_time: <morning | afternoon | night>
link: ""
coords: [lat, lon]         # python3 scripts/geocode.py fills it from OpenStreetMap
verified: YYYY-MM          # when hours/prices/closures were last checked
---

# <Activity name>

## Description

## How to get there

## Tips
