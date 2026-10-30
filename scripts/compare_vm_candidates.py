import pathlib
import numpy as np
import pandas as pd
import geopandas as gpd
import requests

RAW = pathlib.Path("data/raw/chicago")
GJ = RAW / "community_areas.geojson"
if not GJ.exists():
    url = "https://data.cityofchicago.org/api/geospatial/igwz-8jzy?method=export&format=GeoJSON"
    r = requests.get(url, timeout=120)
    if r.status_code != 200 or b"FeatureCollection" not in r.content[:300]:
        raise SystemExit("Download failed: export Boundaries - Community Areas as GeoJSON "
                         "to data/raw/chicago/community_areas.geojson")
    GJ.write_bytes(r.content)
ca = gpd.read_file(GJ).to_crs(4326)
num_col = next(c for c in ca.columns if c.lower().startswith("area_num"))
name_col = next(c for c in ca.columns if c.lower() in ("community", "community_name"))
ca["ca_num"] = ca[num_col].astype(int)
ca["ca_name"] = ca[name_col].str.title()
cent = ca.to_crs(26916).geometry.centroid.to_crs(4326)
ca["lat"], ca["lon"] = cent.y, cent.x
print("community areas loaded:", len(ca))
cands = [("O'Hare Airport", 41.9786, -87.9048), ("Midway Airport", 41.7868, -87.7522),
         ("Vertiport Chicago", 41.8645, -87.6714)]
for a in [8, 32, 6, 28, 7, 24]:
    r = ca[ca["ca_num"] == a].iloc[0]
    cands.append((f"{r['ca_name']} ({a})", r["lat"], r["lon"]))
cands = pd.DataFrame(cands, columns=["name", "lat", "lon"])
cg = gpd.GeoDataFrame(cands, geometry=gpd.points_from_xy(cands.lon, cands.lat), crs=4326)
cj = gpd.sjoin(cg, ca[["ca_num", "geometry"]], how="left", predicate="within")
cands["ca_num"] = cj["ca_num"].values
cand_areas = set(cands["ca_num"])
def km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2 - lon1)
    h = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(h))

vm = pd.read_csv(RAW / "vm2024_cluster_centers.csv")
vg = gpd.GeoDataFrame(vm, geometry=gpd.points_from_xy(vm.lon, vm.lat), crs=4326)
j = gpd.sjoin(vg, ca[["ca_num", "ca_name", "geometry"]], how="left", predicate="within")
rows = []
for _, r in j.iterrows():
    d = km(r["lat"], r["lon"], cands.lat.values, cands.lon.values)
    k = int(np.argmin(d))
    ok = (d[k] <= 2) or (r["ca_num"] in cand_areas)
    rows.append(dict(vm_id=r["id"], vm_area=f"{r['ca_name']} ({int(r['ca_num'])})",
                     nearest=cands.name[k], dist_km=round(d[k], 1), covered="yes" if ok else "NO"))
res = pd.DataFrame(rows)
print(res.to_string(index=False))
print("Covered:", (res.covered == "yes").sum(), "of", len(res))
print("Areas to add:", ", ".join(res[res.covered == "NO"].vm_area))
res.to_csv(RAW / "vm_coverage_check.csv", index=False)
