import pathlib
import duckdb

RAW = "data/raw/nyc/yellow_tripdata_2019-03.parquet"
ZONES = "data/raw/nyc/taxi_zone_lookup.csv"
OUT = pathlib.Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)

con = duckdb.connect()

# 1. Clean weekday morning trips (7:00-9:59), March 2019
con.execute(f"""
CREATE TABLE am AS
SELECT PULocationID AS o, DOLocationID AS d,
       CAST(tpep_pickup_datetime AS DATE) AS day,
       date_diff('second', tpep_pickup_datetime, tpep_dropoff_datetime) / 60.0 AS minutes,
       trip_distance AS miles, fare_amount AS fare, total_amount AS total
FROM read_parquet('{RAW}')
WHERE tpep_pickup_datetime >= '2019-03-01' AND tpep_pickup_datetime < '2019-04-01'
  AND isodow(tpep_pickup_datetime) BETWEEN 1 AND 5
  AND hour(tpep_pickup_datetime) BETWEEN 7 AND 9
  AND PULocationID NOT IN (264, 265) AND DOLocationID NOT IN (264, 265)
  AND PULocationID <> DOLocationID
""")
con.execute("""
DELETE FROM am
WHERE minutes < 1 OR minutes > 180 OR miles <= 0 OR miles > 100 OR fare <= 0
""")

n_days = con.execute("SELECT count(DISTINCT day) FROM am").fetchone()[0]

# 2. Aggregate per origin-destination pair
od = con.execute(f"""
SELECT a.o, zo.Borough AS o_borough, zo.Zone AS o_zone,
       a.d, zd.Borough AS d_borough, zd.Zone AS d_zone,
       count(*) / {n_days} AS trips_per_day,
       avg(minutes) AS avg_min,
       quantile_cont(minutes, 0.5) AS median_min,
       avg(miles) AS avg_miles,
       avg(fare) AS avg_fare,
       avg(total) AS avg_total
FROM am a
JOIN read_csv_auto('{ZONES}') zo ON a.o = zo.LocationID
JOIN read_csv_auto('{ZONES}') zd ON a.d = zd.LocationID
GROUP BY ALL
ORDER BY trips_per_day DESC
""").df()

od.to_csv(OUT / "nyc_od_am_2019-03.csv", index=False)

# 3. Sanity checks
print("weekdays in sample:", n_days)
print("clean AM trips per weekday:", round(od.trips_per_day.sum()))
print("OD pairs:", len(od))
print("\nTop 10 OD pairs:")
print(od.head(10)[["o_zone", "d_zone", "trips_per_day", "median_min"]].to_string(index=False))
airports = od[od.o.isin([132, 138]) | od.d.isin([132, 138])]
print("\nTrips per weekday AM touching JFK (132) or LaGuardia (138):",
      round(airports.trips_per_day.sum()))
print(airports.head(10)[["o_zone", "d_zone", "trips_per_day", "median_min"]].to_string(index=False))
