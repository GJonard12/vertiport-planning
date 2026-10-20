import pathlib, pickle
import numpy as np
import pandas as pd
import yaml

P = pathlib.Path("data/processed")
cfg = yaml.safe_load(open("config/nyc.yaml"))
cent = pd.read_csv(P / "nyc_zone_centroids.csv").set_index("LocationID")
od = pd.read_csv(P / "nyc_od_am_2019-03.csv")

# (b) Candidate vertiport sites: zones of the sites named in the paper's Table 4, plus heliports and hubs
CANDIDATES = [
    "JFK Airport", "LaGuardia Airport", "Newark Airport", "Midtown Center", "Clinton East",
    "Clinton West", "TriBeCa/Civic Center", "Lincoln Square East", "Upper West Side South",
    "Garment District", "Gramercy", "Astoria",                                   # paper, Table 4
    "Battery Park", "Kips Bay", "West Chelsea/Hudson Yards",                     # existing heliports
    "Midtown East", "Times Sq/Theatre District", "Penn Station/Madison Sq West",
    "Financial District North", "Upper East Side South", "Upper East Side North",
    "Long Island City/Hunters Point", "Downtown Brooklyn/MetroTech",
    "Williamsburg (North Side)", "Flushing", "Jamaica",
]
missing = [n for n in CANDIDATES if n not in set(cent.zone)]
if missing:
    raise SystemExit(f"Zone names not found, send me this list: {missing}")
cand_ids = cent.index[cent.zone.isin(CANDIDATES)].tolist()

# Straight-line distances between zone centers (km)
ids = cent.index.to_numpy()
pos = {z: k for k, z in enumerate(ids)}
X, Y = cent.x_ft.to_numpy(), cent.y_ft.to_numpy()
KM = np.hypot(X[:, None] - X[None, :], Y[:, None] - Y[None, :]) * 0.0003048
km = lambda a, b: KM[pos[a], pos[b]]

n0 = len(od)
od = od[od.o.isin(pos) & od.d.isin(pos)].copy()
print(f"dropped {n0 - len(od)} OD rows with zone IDs missing from the map")

# (c) Ground times: observed AM taxi medians when available, else a fitted line on distance
fit = od[od.trips_per_day >= 5]
slope, intercept = np.polyfit([km(a, b) for a, b in zip(fit.o, fit.d)], fit.median_min, 1)
print(f"ground time fit: minutes = {intercept:.1f} + {slope:.2f} x km")
obs = {(a, b): m for a, b, m, n in zip(od.o, od.d, od.median_min, od.trips_per_day) if n >= 1}

def ground(a, b):
    if a == b:
        return cfg["same_zone_access_minutes"]
    return obs.get((a, b), intercept + slope * km(a, b))

def nearest(z, access=True):
    t = [((ground(z, i) if access else ground(i, z)), i) for i in cand_ids]
    t = sorted(x for x in t if x[0] <= cfg["max_access_minutes"])
    return t[: cfg["k_nearest_vertiports"]]

# OD pairs worth considering
odk = od[(od.median_min >= cfg["min_ground_minutes"]) & (od.trips_per_day >= cfg["min_trips_per_day"])].copy()
odk["D"] = odk.trips_per_day * cfg["demand_scale_S"]
acc = {z: nearest(z, True) for z in odk.o.unique()}
egr = {z: nearest(z, False) for z in odk.d.unique()}

# (d) Every option (o, d, i, j): air-taxi time, saving, and share who switch
rows = []
for r in odk.itertuples():
    for t_oi, i in acc[r.o]:
        for t_jd, j in egr[r.d]:
            if i == j:
                continue
            t_f = km(i, j) / cfg["cruise_kmh"] * 60 + cfg["flight_overhead_minutes"]
            tau = t_oi + cfg["pooling_wait_minutes"] + t_f + t_jd
            saving = 1 - tau / r.median_min
            tt = (saving - cfg["mu"]) / cfg["sigma"]
            a = tt**2 / (1 + tt**2) if tt > 0 else 0.0
            if a > 0:
                rows.append(dict(o=r.o, d=r.d, i=i, j=j, D=r.D, t_ground=r.median_min,
                                 t_access=t_oi, t_flight=t_f, t_egress=t_jd, tau=tau,
                                 saving=saving, share=a))
opt = pd.DataFrame(rows)

# Summary
name = cent.zone.to_dict()
print(f"candidate sites: {len(cand_ids)}")
print(f"OD pairs kept (>= {cfg['min_ground_minutes']} min, >= {cfg['min_trips_per_day']} trips/day): {len(odk)}")
print(f"options with a positive share: {len(opt)}, covering {opt.groupby(['o','d']).ngroups} OD pairs")
best = opt.sort_values("share", ascending=False).drop_duplicates(["o", "d"])
best["pax"] = best.D * best.share
print(f"upper bound on air-taxi passengers (all sites open): {best.pax.sum():.0f} per weekday AM")
top = best.sort_values("pax", ascending=False).head(10)
top = top.assign(o=top.o.map(name), d=top.d.map(name), i=top.i.map(name), j=top.j.map(name))
print("\nTop 10 OD pairs by potential air-taxi passengers:")
print(top[["o", "d", "i", "j", "t_ground", "tau", "saving", "share", "pax"]].round(2).to_string(index=False))
use = pd.concat([opt.i, opt.j]).map(name).value_counts()
print("\nHow often each candidate appears in a useful option:")
print(use.to_string())

pickle.dump(dict(cfg=cfg, candidates=cand_ids, od=odk, options=opt), open(P / "nyc_instance.pkl", "wb"))
opt.to_csv(P / "nyc_options.csv", index=False)
print("\nsaved data/processed/nyc_instance.pkl and nyc_options.csv")
