import sys, os, pathlib
import requests
import pandas as pd

DATASETS = {"2019-03": "m6dm-c72p", "2026-03": "6dvr-xwnh"}
month = sys.argv[1]                      # e.g. 2019-03
ds = DATASETS[month]
y, m = map(int, month.split("-"))
start = f"{y}-{m:02d}-01T00:00:00"
end = f"{y + (m == 12)}-{m % 12 + 1:02d}-01T00:00:00"
URL = f"https://data.cityofchicago.org/resource/{ds}.json"
HEAD = {"X-App-Token": os.environ["SOCRATA_TOKEN"]} if "SOCRATA_TOKEN" in os.environ else {}
OUT = pathlib.Path("data/raw/chicago"); OUT.mkdir(parents=True, exist_ok=True)

def get(params):
    r = requests.get(URL, params=params, headers=HEAD, timeout=900)
    if r.status_code != 200:
        raise SystemExit(f"ERROR {r.status_code}: {r.text[:500]}")
    return r.json()

W = (f"trip_start_timestamp >= '{start}' AND trip_start_timestamp < '{end}' "
     "AND shared_trip_authorized = false AND trip_seconds >= 60 AND trip_seconds <= 10800 "
     "AND fare > 0 AND additional_charges IS NOT NULL "
     "AND pickup_community_area IS NOT NULL AND dropoff_community_area IS NOT NULL")
print(f"{month} ({ds}): clean trips =", get({"$select": "count(*)", "$where": W})[0]["count"])

period = ("case(date_extract_dow(trip_start_timestamp) IN (0, 6), 'weekend', "
          "date_extract_hh(trip_start_timestamp) BETWEEN 7 AND 9, 'am', "
          "date_extract_hh(trip_start_timestamp) BETWEEN 10 AND 15, 'midday', "
          "date_extract_hh(trip_start_timestamp) BETWEEN 16 AND 18, 'pm', "
          "true, 'other')")
q = "(fare + additional_charges)"
sel = ("pickup_community_area AS o, dropoff_community_area AS d, " + period + " AS period, "
       "count(*) AS n, avg(trip_seconds) AS sec_mean, avg(trip_miles) AS miles_mean, "
       "avg(fare) AS fare_mean, avg" + q + " AS price_mean, "
       "avg(60 / trip_seconds) AS inv_t, "
       "avg(60 * " + q + " / trip_seconds) AS q_over_t, "
       "avg(3600 / (trip_seconds * trip_seconds)) AS inv_t2, "
       "avg(3600 * " + q + " / (trip_seconds * trip_seconds)) AS q_over_t2, "
       "avg(3600 * " + q + " * " + q + " / (trip_seconds * trip_seconds)) AS q2_over_t2")
print("aggregating on Chicago's server (can take a few minutes)...")
rows = get({"$select": sel, "$where": W, "$group": "o, d, period", "$limit": 100000})
df = pd.DataFrame(rows).apply(pd.to_numeric, errors="ignore")
df.to_csv(OUT / f"tnp_od_period_{month}.csv", index=False)

print(f"rows (OD x period): {len(df)}")
print("\ntrips by period:\n", df.groupby("period").n.sum().to_string())
ohare = df[(df.o == 76) | (df.d == 76)]
print("\ntrips touching O'Hare (area 76) by period:\n", ohare.groupby("period").n.sum().to_string())
print(f"\nsaved data/raw/chicago/tnp_od_period_{month}.csv")
