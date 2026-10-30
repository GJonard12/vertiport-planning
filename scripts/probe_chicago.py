import json
import requests

BASE = "https://data.cityofchicago.org/resource/m6dm-c72p.json"
W = "trip_start_timestamp >= '2019-03-01T00:00:00' AND trip_start_timestamp < '2019-04-01T00:00:00'"

def q(label, params):
    try:
        r = requests.get(BASE, params=params, timeout=300)
        r.raise_for_status()
        print(f"\n{label}:\n", json.dumps(r.json(), indent=1)[:2500])
    except Exception as e:
        print(f"\n{label}: ERROR {e}")

cols = requests.get("https://data.cityofchicago.org/api/views/m6dm-c72p/columns.json", timeout=60).json()
print("Columns:", [c["fieldName"] for c in cols])

q("Sample trips (Mon 4 Mar 2019, 8:00-8:15)",
  {"$limit": 3, "$where": "trip_start_timestamp between '2019-03-04T08:00:00' and '2019-03-04T08:15:00'"})
q("All trips, March 2019", {"$select": "count(*)", "$where": W})
q("Long (>= 20 min), not shared, March 2019",
  {"$select": "count(*)", "$where": W + " AND trip_seconds >= 1200 AND shared_trip_authorized = false"})
q("Trips with missing pickup community area, March 2019",
  {"$select": "count(*)", "$where": W + " AND pickup_community_area IS NULL"})
