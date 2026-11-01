import pathlib
import requests

RAW = pathlib.Path("data/raw/nyc")
RAW.mkdir(parents=True, exist_ok=True)
BASE = "https://d37ci6vzurychx.cloudfront.net"
FILES = {
    "yellow_tripdata_2019-03.parquet": f"{BASE}/trip-data/yellow_tripdata_2019-03.parquet",
    "taxi_zone_lookup.csv": f"{BASE}/misc/taxi_zone_lookup.csv",
    "taxi_zones.zip": f"{BASE}/misc/taxi_zones.zip",
}

for name, url in FILES.items():
    out = RAW / name
    if out.exists():
        print("already have", name)
        continue
    print("downloading", name, "...")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(out, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    print("  saved", out, round(out.stat().st_size / 1e6, 1), "MB")
