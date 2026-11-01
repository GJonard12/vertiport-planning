"""Day-level bootstrap of the Chicago study (16 candidate sites, exact shares, saving floor 0.15).

Resamples the 22 weekdays and 9 weekend days of March 2026 with replacement, rebuilds demand, ground times,
options and switching shares exactly as build_chicago_instance.py + add_shares_v2.py do, and re-solves
P1/P2 (no capacity) by full enumeration of all networks with p = 2..8 sites (Proposition 1 gives each
network's value in closed form, so enumeration is exact and needs no solver).

Usage:  python scripts/bootstrap_days.py [B] [seed]      (default B = 200, seed = 1)
Writes: results/bootstrap_samples.csv (one row per sample x scenario x p) and prints a summary.
"""
import sys, glob, itertools, pathlib, pickle, time, numpy as np, pandas as pd, geopandas as gpd, yaml

B = int(sys.argv[1]) if len(sys.argv) > 1 else 200
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 1
cfg = yaml.safe_load(open("config/chicago.yaml"))
SCEN = ["launch", "adopter", "mature"]
FLOOR, PMIN, PMAX = 0.15, 2, 8
PER = ["am", "midday", "pm", "other", "weekend"]
DAYS_YR = {"am": 250, "midday": 250, "pm": 250, "other": 250, "weekend": 115}
SHRINK_N, SDX_FLOOR = 30, 0.01

# ---------- fixed inputs: zones, candidates, distances ----------
cdf = pickle.load(open("data/processed/chicago_instance.pkl", "rb"))["candidates"]   # the 16 sites, kept fixed
ca = gpd.read_file("data/raw/chicago/community_areas.geojson").to_crs(4326)
num_col = next(c for c in ca.columns if c.lower().startswith("area_num"))
ca["ca_num"] = ca[num_col].astype(int)
cent = ca.to_crs(26916).geometry.centroid.to_crs(4326)
ca["lat"], ca["lon"] = cent.y, cent.x
ca = ca.sort_values("ca_num").reset_index(drop=True)
zones = ca.ca_num.tolist(); idx = {z: k for k, z in enumerate(zones)}

def hav(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    h = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(h))

LAT, LON = ca.lat.to_numpy(), ca.lon.to_numpy()
KM = hav(LAT[:, None], LON[:, None], LAT[None, :], LON[None, :])
cand = cdf.zone.tolist(); ci = np.array([idx[z] for z in cand]); NC = len(cand)
FKM = hav(cdf.lat.values[:, None], cdf.lon.values[:, None], cdf.lat.values[None, :], cdf.lon.values[None, :])

# ---------- daily data ----------
STATS = ["sec_mean", "miles_mean", "fare_mean", "price_mean", "inv_t", "q_over_t", "inv_t2", "q_over_t2", "q2_over_t2"]
day_files = sorted(glob.glob("data/raw/chicago/days_2026-03/*.csv"))
days = {pathlib.Path(f).stem: pd.read_csv(f) for f in day_files if pathlib.Path(f).stat().st_size > 50}
for d in days.values():
    for c in STATS: d[c + "_w"] = d[c] * d.n
wkd = [k for k, d in days.items() if "weekend" not in set(d.period)]
wke = [k for k, d in days.items() if "weekend" in set(d.period)]
print(f"{len(wkd)} weekdays, {len(wke)} weekend days")

def aggregate(draw_wkd, draw_wke):
    allp = pd.concat([days[k] for k in draw_wkd + draw_wke], ignore_index=True)
    g = allp.groupby(["o", "d", "period"])
    out = g.n.sum().to_frame()
    for c in STATS: out[c] = g[c + "_w"].sum() / out.n
    out = out.reset_index()
    out["n_days"] = np.where(out.period == "weekend", len(draw_wke), len(draw_wkd))
    out["trips_per_day"] = out.n / out.n_days
    return out

# ---------- rebuild the instance (same rules as build_chicago_instance.py and add_shares_v2.py) ----------
sl = np.sqrt(np.log(1 + cfg["vot_cv"] ** 2))
zk, wk = np.polynomial.hermite.hermgauss(24); zk, wk = np.sqrt(2) * zk, wk / np.sqrt(np.pi)

def Phi(x):
    z = np.abs(x) / np.sqrt(2); t = 1 / (1 + 0.3275911 * z)
    y = 1 - t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429)))) * np.exp(-z * z)
    return 0.5 * (1 + np.sign(x) * y)

def exact(sv, EX, sdX, bmed):
    b = bmed * np.exp(sl * zk)
    return (wk * Phi((np.multiply.outer(sv, b) - EX[..., None]) / sdX[..., None])).sum(-1)

def build(df):
    df = df.copy(); df["minutes"] = df.sec_mean / 60
    G = {}
    for p in PER:
        sub = df[(df.period == p) & (df.o != df.d)]
        fit = sub[sub.trips_per_day >= 5]
        beta, alpha = np.polyfit(KM[fit.o.map(idx).values, fit.d.map(idx).values], fit.minutes.values, 1)
        M = alpha + beta * KM
        good = sub[sub.trips_per_day >= cfg["obs_min_trips_per_day"]]
        M[good.o.map(idx).values, good.d.map(idx).values] = good.minutes.values
        np.fill_diagonal(M, cfg["same_zone_access_minutes"]); G[p] = M
    od = df[(df.o != df.d) & (df.minutes >= cfg["min_ground_minutes"])
            & (df.trips_per_day >= cfg["min_trips_per_day"])].copy().reset_index(drop=True)
    od["miles"] = KM[od.o.map(idx).values, od.d.map(idx).values] * 0.621371
    rows, K, amax = [], cfg["k_nearest_vertiports"], cfg["max_access_minutes"]
    for p in PER:
        Gp = G[p]
        for r in od[od.period == p].itertuples():
            acc, egr = Gp[idx[r.o], ci], Gp[ci, idx[r.d]]
            ia = [a for a in np.argsort(acc)[:K] if acc[a] <= amax]
            je = [e for e in np.argsort(egr)[:K] if egr[e] <= amax]
            for a in ia:
                for e in je:
                    if a == e: continue
                    tf = FKM[a, e] / cfg["cruise_kmh"] * 60 + cfg["flight_overhead_minutes"]
                    sv = 1 - (acc[a] + cfg["pooling_wait_minutes"] + tf + egr[e]) / r.minutes
                    if sv > cfg["keep_saving_above"]: rows.append((r.Index, p, a, e, sv))
    opt = pd.DataFrame(rows, columns=["od_row", "period", "ia", "je", "saving"])
    w = od.trips_per_day.to_numpy(); rr = opt.od_row.to_numpy(); grid = np.linspace(0, 1, 201)
    for s in SCEN:
        sc = cfg["scenarios"][s]; bmed = sc["vot"] / 60
        P = sc["base"] + sc["rate"] * od.miles
        EX = (P * od.inv_t - od.q_over_t).to_numpy()
        VX = (P**2 * od.inv_t2 - 2*P*od.q_over_t2 + od.q2_over_t2).to_numpy() - EX**2 - (2.5**2/12) * od.inv_t2.to_numpy()
        sdX = np.sqrt(np.clip(VX, 0, None))
        prior = od.assign(sdX=sdX).groupby("period").sdX.median()
        n = od.n.to_numpy()
        sdX = np.maximum((n * sdX + SHRINK_N * od.period.map(prior).to_numpy()) / (n + SHRINK_N), SDX_FLOOR)
        opt[f"x_het_{s}"] = exact(opt.saving.to_numpy(), EX[rr], sdX[rr], bmed)
        pooled = np.array([np.average(exact(np.full(len(EX), g), EX, sdX, bmed), weights=w) for g in grid])
        opt[f"x_uni_{s}"] = np.interp(opt.saving.to_numpy(), grid, pooled)
    opt["D"] = od.trips_per_day.to_numpy()[rr]
    return od, opt

# ---------- exact evaluation of every network with p = 2..8 (Proposition 1) ----------
SUBSETS = {p: np.array(list(itertools.combinations(range(NC), p))) for p in range(PMIN, PMAX + 1)}
SUBMASK = {p: np.zeros((len(S), NC), bool) for p, S in SUBSETS.items()}
for p, S in SUBSETS.items(): SUBMASK[p][np.arange(len(S))[:, None], S] = True

def analyse(opt):
    """For every scenario and p: robust network, single-period plans, regrets, weekday VOH and forecast error."""
    o = opt[opt.saving >= FLOOR].sort_values("od_row")
    starts = np.flatnonzero(np.r_[True, o.od_row.to_numpy()[1:] != o.od_row.to_numpy()[:-1]])
    per = o.period.to_numpy()[starts]; yr = o.period.map(DAYS_YR).to_numpy()
    ia, je = o.ia.to_numpy(), o.je.to_numpy(); rows = []
    for p in range(PMIN, PMAX + 1):
        M = SUBMASK[p]; open_ = M[:, ia] & M[:, je]                         # networks x options
        V = {}
        for s in SCEN:
            for k in ("het", "uni"):
                v = (o[f"x_{k}_{s}"].to_numpy() * o.D.to_numpy() * yr).astype(np.float32)
                best = np.maximum.reduceat(open_ * v, starts, axis=1)       # networks x OD rows
                V[s, k] = np.stack([best[:, per == t].sum(1) for t in PER], axis=1)
        for s in SCEN:
            Vh, Vu = V[s, "het"], V[s, "uni"]
            tot = Vh.sum(1); r = tot.argmax(); best = tot[r]
            row = dict(scenario=s, p=p, annual_k=best / 1e3, robust=tuple(cand[c] for c in SUBSETS[p][r]))
            for k, t in enumerate(PER):
                a = Vh[:, k].argmax()
                row[f"regret_{t}"] = 100 * (best - tot[a]) / best if best else 0.0
                row[f"plan_{t}"] = tuple(cand[c] for c in SUBSETS[p][a])
                row[f"{t}_k"] = Vh[r, k] / 1e3
            wk_h, wk_u = Vh[:, :4].sum(1), Vu[:, :4].sum(1)                 # weekday: VOH and forecast error
            h, u = wk_h.argmax(), wk_u.argmax()
            row["VOH_weekday"] = 100 * (wk_h[h] - wk_h[u]) / wk_h[h] if wk_h[h] else 0.0
            row["fcst_err_weekday"] = 100 * (wk_u[u] - wk_h[u]) / wk_h[u] if wk_h[u] else 0.0
            rows.append(row)
    return rows

if __name__ == "__main__":
    t0 = time.time()
    od, opt = build(aggregate(wkd, wke))
    base = pd.DataFrame(analyse(opt)).assign(sample=0)
    print(f"original month rebuilt and solved in {time.time() - t0:.0f} s")
    rng = np.random.default_rng(SEED); out = [base]
    for b in range(1, B + 1):
        dw = list(rng.choice(wkd, len(wkd))); de = list(rng.choice(wke, len(wke)))
        od, opt = build(aggregate(dw, de))
        out.append(pd.DataFrame(analyse(opt)).assign(sample=b))
        if b % 10 == 0: print(f"  {b}/{B} samples, {time.time() - t0:.0f} s")
    R = pd.concat(out, ignore_index=True)
    for c in [c for c in R.columns if c == "robust" or c.startswith("plan_")]: R[c] = R[c].apply(lambda t: "-".join(map(str, t)))
    pathlib.Path("results").mkdir(exist_ok=True); R.to_csv("results/bootstrap_samples.csv", index=False)
    print("saved results/bootstrap_samples.csv")
