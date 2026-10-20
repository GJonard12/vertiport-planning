import pathlib, zipfile
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

RAW = pathlib.Path("data/raw/nyc")
OUT = pathlib.Path("data/processed")
FIG = pathlib.Path("figures"); FIG.mkdir(exist_ok=True)

# 1. Read the taxi zone map (NY State Plane, units = feet)
zdir = RAW / "taxi_zones"
if not zdir.exists():
    zipfile.ZipFile(RAW / "taxi_zones.zip").extractall(zdir)
zones = gpd.read_file(next(zdir.rglob("*.shp")))
zones = zones.dissolve(by="LocationID", as_index=False, aggfunc="first")  # a few IDs have several polygons

# 2. Zone centroids (instance sub-step a), saved for later
cent = zones[["LocationID", "zone", "borough"]].copy()
c = zones.geometry.centroid
c_ll = gpd.GeoSeries(c, crs=zones.crs).to_crs(4326)
cent["x_ft"], cent["y_ft"] = c.x, c.y
cent["lon"], cent["lat"] = c_ll.x, c_ll.y
cent.to_csv(OUT / "nyc_zone_centroids.csv", index=False)

# 3. Weekday-morning trips starting or ending in each zone
od = pd.read_csv(OUT / "nyc_od_am_2019-03.csv")
ends = od.groupby("o").trips_per_day.sum().add(od.groupby("d").trips_per_day.sum(), fill_value=0)
zones["trip_ends"] = zones.LocationID.map(ends)

def pt(name):
    r = cent[cent.zone == name]
    assert len(r) == 1, f"zone not found: {name}"
    return r.iloc[0]

def km(a, b):
    return np.hypot(a.x_ft - b.x_ft, a.y_ft - b.y_ft) * 0.0003048

# 4. Map
city = zones[~zones.borough.isin(["Staten Island", "EWR"])]
fig, ax = plt.subplots(figsize=(11, 11))
fig.patch.set_facecolor("#fcfcfb")
zones.plot(ax=ax, color="#eeede9", edgecolor="white", linewidth=0.4)
city.plot(ax=ax, column="trip_ends", cmap="Blues",
          norm=LogNorm(vmin=1, vmax=city.trip_ends.max()),
          edgecolor="white", linewidth=0.4, legend=True,
          legend_kwds={"label": "taxi trips starting or ending in zone, weekday 7-10 am (log scale)", "shrink": 0.55},
          missing_kwds={"color": "#eeede9"})

trips = [("JFK Airport", "Midtown Center", 70, 31, "#eb6834", (40, -40)),
         ("LaGuardia Airport", "Midtown Center", 44, 27, "#c98500", (30, 35)),
         ("Upper East Side South", "Midtown Center", 10, 19, "#6250d6", (-210, 25))]
print("Straight-line distances:")
for o, d, taxi, air, col, off in trips:
    a, b = pt(o), pt(d)
    dist = km(a, b)
    print(f"  {o} -> {d}: {dist:.1f} km, taxi {taxi} min")
    ax.annotate("", xy=(b.x_ft, b.y_ft), xytext=(a.x_ft, a.y_ft),
                arrowprops=dict(arrowstyle="-|>", color=col, lw=2.5, mutation_scale=18))
    mid = ((a.x_ft + b.x_ft) / 2, (a.y_ft + b.y_ft) / 2)
    ax.annotate(f"{o.replace(' Airport','')} to Midtown\n{dist:.0f} km straight line\ntaxi {taxi} min, air taxi ~{air} min",
                xy=mid, xytext=off, textcoords="offset points", fontsize=9.5, color="#0b0b0b",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=col, lw=1.5))

for nm in ["JFK Airport", "Clinton East", "Astoria"]:
    p = pt(nm)
    ax.scatter(p.x_ft, p.y_ft, marker="*", s=420, color="#e34948", edgecolor="white", linewidth=1.2, zorder=5)
ax.scatter([], [], marker="*", s=200, color="#e34948", label="paper's 3 vertiports at mu = 0.40 (Astoria approx.)")
ax.legend(loc="upper left", frameon=False, fontsize=10)

xmin, ymin, xmax, ymax = city.total_bounds
ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax); ax.axis("off")
ax.set_title("NYC: where the morning taxi demand is, and the three example trips from Figure 2",
             loc="left", fontsize=13, fontweight="bold")
fig.savefig(FIG / "nyc_map_part1.png", dpi=160, bbox_inches="tight")
print("saved figures/nyc_map_part1.png and data/processed/nyc_zone_centroids.csv")
