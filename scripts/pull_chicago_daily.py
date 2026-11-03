import sys, os, time, pathlib, datetime as dt
import requests
import pandas as pd

DATASETS = {"2019-03": "m6dm-c72p", "2026-03": "6dvr-xwnh"}
month = sys.argv[1]
ds = DATASETS.get(month) or ("6dvr-xwnh" if month >= "2025" else "n26f-ihde" if month >= "2023" else "m6dm-c72p")
y, m = map(int, month.split("-"))
first, nxt = dt.date(y, m, 1), dt.date(y + (m == 12), m % 12 + 1, 1)
URL = f"https://data.cityofchicago.org/resource/{ds}.json"
HEAD = {"X-App-Token": os.environ["SOCRATA_TOKEN"]} if "SOCRATA_TOKEN" in os.environ else {}
RAW = pathlib.Path("data/raw/chicago")
DAYS = RAW / f"days_{month}"
DAYS.mkdir(parents=True, exist_ok=True)

def get(params, tries=4):
    for k in range(tries):
        try:
            r = requests.get(URL, params=params, headers=HEAD, timeout=600)
            if r.status_code == 200:
                return r.json()
            print(f"   HTTP {r.status_code}: {r.text[:200]}")
        except requests.exceptions.RequestException as e:
            print(f"   {type(e).__name__}")
        wait = 30 * (k + 1)
        print(f"   retrying in {wait} s ...")
        time.sleep(wait)
    raise SystemExit("Giving up for now. Rerun the same command later: finished days are kept.")

FILTERS = ("shared_trip_authorized = false AND trip_seconds >= 60 AND trip_seconds <= 10800 "
           "AND fare > 0 AND additional_charges IS NOT NULL "
           "AND pickup_community_area IS NOT NULL AND dropoff_community_area IS NOT NULL")
PERIOD = ("case(date_extract_dow(trip_start_timestamp) IN (0, 6), 'weekend', "
          "date_extract_hh(trip_start_timestamp) BETWEEN 7 AND 9, 'am', "
          "date_extract_hh(trip_start_timestamp) BETWEEN 10 AND 15, 'midday', "
          "date_extract_hh(trip_start_timestamp) BETWEEN 16 AND 18, 'pm', "
          "true, 'other')")
Q = "(fare + additional_charges)"
STATS = {"sec_mean": "trip_seconds", "miles_mean": "trip_miles", "fare_mean": "fare",
         "price_mean": Q,
         "inv_t": "60 / trip_seconds",
         "q_over_t": f"60 * {Q} / trip_seconds",
         "inv_t2": "3600 / (trip_seconds * trip_seconds)",
         "q_over_t2": f"3600 * {Q} / (trip_seconds * trip_seconds)",
         "q2_over_t2": f"3600 * {Q} * {Q} / (trip_seconds * trip_seconds)"}
SELECT = ("pickup_community_area AS o, dropoff_community_area AS d, " + PERIOD + " AS period, count(*) AS n, "
          + ", ".join(f"avg({expr}) AS {name}" for name, expr in STATS.items()))
COLS = ["o", "d", "period", "n"] + list(STATS)

# 1. One query per day (skips days already saved)
day = first
while day < nxt:
    f = DAYS / f"{day}.csv"
    if f.exists():
        print(f"{day}: already done")
    else:
        t0 = time.time()
        W = f"trip_start_timestamp >= '{day}T00:00:00' AND trip_start_timestamp < '{day + dt.timedelta(days=1)}T00:00:00' AND " + FILTERS
        rows = get({"$select": SELECT, "$where": W, "$group": "o, d, period", "$limit": 50000})
        df = pd.DataFrame(rows, columns=COLS)
        df.to_csv(f, index=False)
        trips = pd.to_numeric(df.n).sum() if len(df) else 0
        print(f"{day}: {len(df):5d} rows, {trips:8,.0f} trips, {time.time() - t0:4.0f} s")
    day += dt.timedelta(days=1)

# 2. Combine days: trip-weighted averages are exact
parts = [pd.read_csv(p).assign(date=p.stem) for p in sorted(DAYS.glob("*.csv")) if p.stat().st_size > 50]
allp = pd.concat(parts, ignore_index=True)
for c in STATS:
    allp[c + "_w"] = allp[c] * allp.n
g = allp.groupby(["o", "d", "period"])
out = g.n.sum().to_frame()
for c in STATS:
    out[c] = g[c + "_w"].sum() / out.n
out = out.reset_index()
days_per_period = allp.groupby("period").date.nunique()
out["n_days"] = out.period.map(days_per_period)
out["trips_per_day"] = out.n / out.n_days
out.to_csv(RAW / f"tnp_od_period_{month}.csv", index=False)

print(f"\ndays combined: {allp.date.nunique()}, total clean trips: {out.n.sum():,.0f}")
print(f"rows (OD x period): {len(out)}")
print("\ntrips per day by period:\n", (out.groupby('period').n.sum() / days_per_period).round(0).to_string())
oh = out[(out.o == 76) | (out.d == 76)]
print("\nO'Hare (area 76) trips per day by period:\n", (oh.groupby('period').n.sum() / days_per_period).round(0).to_string())
print(f"\nsaved {RAW / f'tnp_od_period_{month}.csv'}")
