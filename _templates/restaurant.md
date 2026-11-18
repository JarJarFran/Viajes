---
id: <city>-restaurant-<slug>
type: restaurant
name: <Restaurant name>
place: <country>/<region>/<city>
area: <city>-area-<slug>
area_detail: <exact spot, optional>
cuisine: <ramen | sushi | izakaya | ...>
price_range: ¥¥            # bucket per person; derived by sync.py from the budgets when they exist
budget_lunch: [1000, 1999]    # per person, local currency: Tabelog budget ranges when known ([null, 999] = under 999)
budget_dinner: [2000, 2999]
tabelog: "https://tabelog.com/en/<pref>/<A..>/<A..>/<id>/"   # the restaurant's own page
tabelog_list: ""           # list page where the score was read, when the own page is unknown
tabelog_rating: 3.50       # optional (omit for places without a score)
# outside Japan (no Tabelog): `link` is required; `guide: michelin-bib` (or michelin-selected / black-pearl)
# counts as the quality signal of the strict shortlist
tags: []                   # `top-rated` is added/removed by sync.py (rating >= 3.5)
station: <nearest station>
station_m: 200
coords: [lat, lon]
verified: YYYY-MM
---

# <Restaurant name>

## What to order

## Hours & booking

## Tips
