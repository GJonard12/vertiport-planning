"""Seasonal check: rebuild the instance for each month and compare networks (adopter, 16 sites, floor 0.15).
Usage: python scripts/compare_months.py 2025-07 2026-01 2026-03"""
import sys, itertools, numpy as np, pandas as pd
MONTHS = sys.argv[1:] or ["2026-03"]
sys.argv = sys.argv[:1]                                   # keep bootstrap_days from reading our args
sys.path.insert(0, "scripts")
import bootstrap_days as bd                               # same build rules and exact evaluation

S, PS = "adopter", [4, 5, 6, 7]
name = dict(zip(bd.cdf.zone, bd.cdf.name))
sites = lambda net: ", ".join(name[z] for z in net)

def network_values(opt, p):                               # yearly passengers of every p-site network
    o = opt[opt.saving >= bd.FLOOR].sort_values("od_row")
    starts = np.flatnonzero(np.r_[True, o.od_row.to_numpy()[1:] != o.od_row.to_numpy()[:-1]])
    M = bd.SUBMASK[p]; open_ = M[:, o.ia.to_numpy()] & M[:, o.je.to_numpy()]
    v = (o[f"x_het_{S}"] * o.D * o.period.map(bd.DAYS_YR)).to_numpy(np.float32)
    return np.maximum.reduceat(open_ * v, starts, axis=1).sum(1)

V, rows = {}, []
for m in MONTHS:
    df = pd.read_csv(f"data/raw/chicago/tnp_od_period_{m}.csv")
    od, opt = bd.build(df)
    day = df.groupby("period").trips_per_day.sum()
    oh = df[(df.o == 76) | (df.d == 76)].groupby("period").trips_per_day.sum()
    print(f"\n=== {m}: trips/day weekday {day.drop('weekend').sum():,.0f}, weekend {day['weekend']:,.0f}; "
          f"O'Hare trips/weekday {oh.drop('weekend', errors='ignore').sum():,.0f}")
    A = pd.DataFrame(bd.analyse(opt)); A = A[(A.scenario == S) & A.p.isin(PS)]
    print(A[["p", "annual_k", "regret_am", "regret_midday", "regret_pm", "VOH_weekday", "fcst_err_weekday"]].round(1).to_string(index=False))
    for r in A.itertuples(): print(f"  p={r.p} robust: {sites(r.robust)}")
    for p in PS: V[m, p] = network_values(opt, p)

# Cross-season: build the network for month a, operate it in month b
print("\nPassengers lost (%) when the network is planned for one month and operated in another (rows = planned, cols = operated):")
for p in PS:
    best = {m: V[m, p].max() for m in MONTHS}
    plan = {a: V[a, p].argmax() for a in MONTHS}
    pooled = np.sum([V[m, p] / best[m] for m in MONTHS], axis=0).argmax()   # all-season network, months weighted equally
    T = pd.DataFrame({b: {a: 100 * (1 - V[b, p][plan[a]] / best[b]) for a in MONTHS} for b in MONTHS})
    T.loc["ALL-SEASON"] = [100 * (1 - V[b, p][pooled] / best[b]) for b in MONTHS]
    print(f"\np = {p}"); print(T.round(1).to_string())
    for a in MONTHS: print(f"  {a}: {sites([bd.cand[c] for c in bd.SUBSETS[p][plan[a]]])}")
    print(f"  ALL-SEASON: {sites([bd.cand[c] for c in bd.SUBSETS[p][pooled]])}")
