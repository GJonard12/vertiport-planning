import pathlib
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

P, FIG = pathlib.Path("data/processed"), pathlib.Path("figures")
zones = gpd.read_file(next(pathlib.Path("data/raw/nyc/taxi_zones").rglob("*.shp")))
zones = zones.dissolve(by="LocationID", as_index=False, aggfunc="first")
cent = pd.read_csv(P / "nyc_zone_centroids.csv")
xy = {z: (x, y) for z, x, y in zip(cent.zone, cent.x_ft, cent.y_ft)}

# Our networks: output of solve_nyc_mu_sweep.py (19 Oct, c = 36.75, sigma = 0.20)
OURS = {0.40: ["JFK Airport", "Times Sq/Theatre District", "Gramercy"],
        0.33: ["JFK Airport", "Times Sq/Theatre District", "Gramercy", "LaGuardia Airport",
               "Midtown Center", "TriBeCa/Civic Center", "Upper East Side North"]}
# Paper, Table 4
base = ["JFK Airport", "Clinton East", "Astoria"]
PAPER = {0.40: base,
         0.33: base + ["Clinton West", "Midtown Center", "Garment District", "TriBeCa/Civic Center",
                       "Upper West Side South", "Gramercy", "Newark Airport"]}

def km(a, b):
    (x1, y1), (x2, y2) = xy[a], xy[b]
    return np.hypot(x1 - x2, y1 - y2) * 0.0003048

fig, axes = plt.subplots(1, 2, figsize=(16, 9))
fig.patch.set_facecolor("#fcfcfb")
view = zones[~zones.borough.isin(["Staten Island"])]
for ax, mu in zip(axes, [0.40, 0.33]):
    zones.plot(ax=ax, color="#eeede9", edgecolor="white", linewidth=0.4)
    print(f"\nmu = {mu}: paper site -> nearest of our sites")
    dists = []
    for s in PAPER[mu]:
        near = min(OURS[mu], key=lambda o: km(s, o))
        d = km(s, near); dists.append(d)
        print(f"  {s:25s} -> {near:28s} {d:5.1f} km")
        (x1, y1), (x2, y2) = xy[s], xy[near]
        if d > 0.05:
            ax.plot([x1, x2], [y1, y2], color="#52514e", lw=1, ls="--", zorder=3)
    print(f"  paper sites with one of ours within 2 km: {sum(d <= 2 for d in dists)} of {len(dists)}")
    px = [xy[s] for s in PAPER[mu]]; ox = [xy[s] for s in OURS[mu]]
    ax.scatter([p[0] for p in px], [p[1] for p in px], marker="*", s=420, color="#e34948",
               edgecolor="white", linewidth=1.2, zorder=5, label="paper (Table 4)")
    ax.scatter([p[0] for p in ox], [p[1] for p in ox], marker="o", s=150, facecolor="none",
               edgecolor="#2a78d6", linewidth=2.5, zorder=6, label="my model")
    xmin, ymin, xmax, ymax = view.total_bounds
    ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax); ax.axis("off")
    ax.set_title(f"mu = {mu:.2f}: paper {len(PAPER[mu])} sites, mine {len(OURS[mu])}", loc="left",
                 fontsize=13, fontweight="bold")
    ax.legend(loc="upper left", frameon=False, fontsize=11)
fig.suptitle("NYC vertiports: Wang, Jacquillat and Vaze (2022) vs my simplified model (no operations layer)",
             x=0.01, ha="left", fontsize=14, fontweight="bold")
fig.savefig(FIG / "nyc_mine_vs_paper.png", dpi=160, bbox_inches="tight")
print("\nsaved figures/nyc_mine_vs_paper.png")
