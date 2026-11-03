import pathlib, pickle
import numpy as np
import pandas as pd
import geopandas as gpd
import yaml, sys

cfg = yaml.safe_load(open(sys.argv[1] if len(sys.argv) > 1 else "config/chicago.yaml"))
TAG = cfg.get("tag", "chicago")
RAW, OUT = pathlib.Path("data/raw/chicago"), pathlib.Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)
df = pd.read_csv(RAW / f"tnp_od_period_{cfg['month']}.csv")
df["minutes"] = df.sec_mean / 60

# Community areas: number, name, centroid
ca = gpd.read_file(RAW / "community_areas.geojson").to_crs(4326)
num_col = next(c for c in ca.columns if c.lower().startswith("area_num"))
name_col = next(c for c in ca.columns if c.lower() in ("community", "community_name"))
ca["ca_num"] = ca[num_col].astype(int)
ca["ca_name"] = ca[name_col].str.title()
cent = ca.to_crs(26916).geometry.centroid.to_crs(4326)
ca["lat"], ca["lon"] = cent.y, cent.x
ca = ca.sort_values("ca_num").reset_index(drop=True)
zones = ca.ca_num.tolist()
idx = {z: k for k, z in enumerate(zones)}
zname = dict(zip(ca.ca_num, ca.ca_name))

def hav(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    h = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(h))

LAT, LON = ca.lat.to_numpy(), ca.lon.to_numpy()
KM = hav(LAT[:, None], LON[:, None], LAT[None, :], LON[None, :])

# Ground-time matrix per period: observed mean if enough trips, else fitted line on distance
G = {}
for p in cfg["periods"]:
    sub = df[(df.period == p) & (df.o != df.d)]
    fit = sub[sub.trips_per_day >= 5]
    beta, alpha = np.polyfit(KM[fit.o.map(idx).values, fit.d.map(idx).values], fit.minutes.values, 1)
    M = alpha + beta * KM
    good = sub[sub.trips_per_day >= cfg["obs_min_trips_per_day"]]
    M[good.o.map(idx).values, good.d.map(idx).values] = good.minutes.values
    np.fill_diagonal(M, cfg["same_zone_access_minutes"])
    G[p] = M
    print(f"{p:8s} ground time fit: {alpha:5.1f} + {beta:4.2f} x km; observed pairs used: {len(good)}")

# Candidate sites: aviation sites (exact points) + demand hubs + V&M additions + coverage rule
SITES = {76: ("O'Hare Airport", 41.9786, -87.9048), 56: ("Midway Airport", 41.7868, -87.7522),
         28: ("Vertiport Chicago", 41.8645, -87.6714)}
cand = list(dict.fromkeys(list(SITES) + cfg["demand_hub_areas"] + cfg["vm_added_areas"]))
if cfg.get("all_candidates"):
    cand = list(dict.fromkeys(cand + zones))
source = {z: ("aviation site" if z in SITES else "demand hub" if z in cfg["demand_hub_areas"]
              else "V&M center" if z in cfg["vm_added_areas"] else "all areas") for z in cand}
Gc, cov = G[cfg["coverage_period"]], cfg["coverage_minutes"]
weight = df.groupby("o").trips_per_day.sum()

def uncovered(c):
    cols = [idx[i] for i in c]
    return [z for z in zones if Gc[idx[z], cols].min() > cov]

unc = uncovered(cand)
while unc:
    best = max((z for z in zones if z not in cand),
               key=lambda z: (sum(Gc[idx[u], idx[z]] <= cov for u in unc), weight.get(z, 0)))
    cand.append(best)
    source[best] = "coverage"
    unc = uncovered(cand)

cdf = pd.DataFrame({"zone": cand})
cdf["name"] = [SITES[z][0] if z in SITES else zname[z] for z in cand]
cdf["lat"] = [SITES[z][1] if z in SITES else LAT[idx[z]] for z in cand]
cdf["lon"] = [SITES[z][2] if z in SITES else LON[idx[z]] for z in cand]
cdf["source"] = [source[z] for z in cand]
FKM = hav(cdf.lat.values[:, None], cdf.lon.values[:, None], cdf.lat.values[None, :], cdf.lon.values[None, :])
print(f"\ncandidates: {len(cdf)}")
print(cdf.to_string(index=False))

# OD pairs worth considering
od = df[(df.o != df.d) & (df.minutes >= cfg["min_ground_minutes"])
        & (df.trips_per_day >= cfg["min_trips_per_day"])].copy().reset_index(drop=True)
od["miles"] = KM[od.o.map(idx).values, od.d.map(idx).values] * 0.621371

# RQ1: OD-specific mu, sigma with lognormal VOT (exact from the 5 sufficient statistics)
s2 = np.log(1 + cfg["vot_cv"] ** 2)
for s, sc in cfg["scenarios"].items():
    m = np.log(sc["vot"] / 60)                       # $ per minute
    e1, e2 = np.exp(-m + s2 / 2), np.exp(-2 * m + 2 * s2)
    P = sc["base"] + sc["rate"] * od.miles
    mu = e1 * (P * od.inv_t - od.q_over_t)
    m2 = e2 * (P ** 2 * od.inv_t2 - 2 * P * od.q_over_t2 + od.q2_over_t2)
    var = m2 - mu ** 2 - e2 * (2.5 ** 2 / 12) * od.inv_t2   # remove $2.50 fare-rounding noise
    od[f"P_{s}"], od[f"mu_{s}"] = P, mu
    od[f"sig_{s}"] = np.sqrt(np.clip(var, cfg["sigma_floor"] ** 2, None))

# Options (period, o, i, j, d)
rows, K, amax = [], cfg["k_nearest_vertiports"], cfg["max_access_minutes"]
ci = np.array([idx[z] for z in cand])
for p in cfg["periods"]:
    Gp = G[p]
    for r in od[od.period == p].itertuples():
        acc, egr = Gp[idx[r.o], ci], Gp[ci, idx[r.d]]
        ia = [a for a in np.argsort(acc)[:K] if acc[a] <= amax]
        je = [e for e in np.argsort(egr)[:K] if egr[e] <= amax]
        for a in ia:
            for e in je:
                if a == e:
                    continue
                tf = FKM[a, e] / cfg["cruise_kmh"] * 60 + cfg["flight_overhead_minutes"]
                tau = acc[a] + cfg["pooling_wait_minutes"] + tf + egr[e] + cfg.get("hassle_minutes", 0)
                sv = 1 - tau / r.minutes
                if sv > cfg["keep_saving_above"]:
                    rows.append((r.Index, p, r.o, r.d, cand[a], cand[e], acc[a], tf, egr[e], tau, sv))
opt = pd.DataFrame(rows, columns=["od_row", "period", "o", "d", "i", "j", "t_acc", "t_flight",
                                  "t_egr", "tau", "saving"])

def share(sv, mu, sig):
    tt = (sv - mu) / sig
    return np.where(tt > 0, tt ** 2 / (1 + tt ** 2), 0.0)

w = od.trips_per_day
for s in cfg["scenarios"]:
    mu_bar, sig_bar = np.average(od[f"mu_{s}"], weights=w), np.average(od[f"sig_{s}"], weights=w)
    opt[f"a_het_{s}"] = share(opt.saving, od.loc[opt.od_row, f"mu_{s}"].values, od.loc[opt.od_row, f"sig_{s}"].values)
    opt[f"a_uni_{s}"] = share(opt.saving, mu_bar, sig_bar)
    od[f"mu_bar_{s}"], od[f"sig_bar_{s}"] = mu_bar, sig_bar

# Summary
print("\nOD pairs kept and options, by period:")
print(pd.DataFrame({"od_pairs": od.groupby("period").size(), "trips_per_day": od.groupby("period").trips_per_day.sum().round(0),
                    "options": opt.groupby("period").size()}).to_string())
print("\nUpper bound on air-taxi passengers per day (all candidates open, best option per OD):")
tab = {}
for s in cfg["scenarios"]:
    for kind in ["het", "uni"]:
        best = opt.groupby("od_row")[f"a_{kind}_{s}"].max()
        pax = (best * od.loc[best.index, "trips_per_day"]).groupby(od.loc[best.index, "period"]).sum()
        tab[f"{s}_{kind}"] = pax.round(0)
print(pd.DataFrame(tab).fillna(0).to_string())
print("\nSpread of OD-specific mu (10th / 50th / 90th percentile) vs the uniform benchmark:")
for s in cfg["scenarios"]:
    q10, q50, q90 = np.percentile(od[f"mu_{s}"], [10, 50, 90])
    print(f"  {s:12s} mu_od {q10:5.2f} / {q50:5.2f} / {q90:5.2f}   uniform mu = {od[f'mu_bar_{s}'].iloc[0]:5.2f}, sigma = {od[f'sig_bar_{s}'].iloc[0]:4.2f}")
best = opt.loc[opt.groupby("od_row").a_het_adopter.idxmax()]
best = best.assign(pax=best.a_het_adopter * od.loc[best.od_row, "trips_per_day"].values).nlargest(10, "pax")
for c in ["o", "d", "i", "j"]:
    best[c] = best[c].map(zname)
print("\nTop 10 OD x period by potential passengers, adopter scenario:")
print(best[["period", "o", "d", "i", "j", "tau", "saving", "a_het_adopter", "pax"]].round(2).to_string(index=False))

pickle.dump(dict(cfg=cfg, zones=ca.drop(columns="geometry"), candidates=cdf, od=od, options=opt, G=G, FKM=FKM),
            open(OUT / f"{TAG}_instance.pkl", "wb"))
cdf.to_csv(OUT / f"{TAG}_candidates.csv", index=False)
print(f"\nsaved data/processed/{TAG}_instance.pkl and {TAG}_candidates.csv")
