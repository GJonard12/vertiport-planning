import argparse, os, pickle, numpy as np, pandas as pd
import gurobipy as gp
from gurobipy import GRB

ap = argparse.ArgumentParser()
ap.add_argument("--instance", default="chicago")
ap.add_argument("--scenario", default="adopter")
ap.add_argument("--floor", type=float, default=0.15)
ap.add_argument("--caps", default="0,200,100,50")   # passengers per hour per vertiport (dep + arr); 0 = no limit
ap.add_argument("--pmin", type=int, default=2)
ap.add_argument("--pmax", type=int, default=8)
A = ap.parse_args()
RES = "results" if A.instance == "chicago" else f"results_{A.instance}"

I = pickle.load(open(f"data/processed/{A.instance}_instance.pkl", "rb"))
od, opt, cdf = I["od"], I["options"].copy(), I["candidates"]
name = dict(zip(cdf.zone, cdf.name)); V = cdf.zone.tolist()
col = f"x_het_{A.scenario}"
opt = opt[(opt.saving >= A.floor) & (opt[col] > 0)].reset_index(drop=True)
DAYS = {"am": 250, "midday": 250, "pm": 250, "other": 250, "weekend": 115}
HOURS = {"am": 3, "midday": 6, "pm": 3, "other": 12, "weekend": 24}    # 7-10, 10-16, 16-19, rest, full day
PER = list(DAYS)
opt["day"] = opt[col] * od.loc[opt.od_row, "trips_per_day"].values    # passengers per day of that period type
opt["val"] = opt.day * opt.period.map(DAYS).values                     # passengers per year
opt["hour"] = opt.day / opt.period.map(HOURS).values                   # passengers per hour (spread evenly)

rows = []
for Q in [float(q) for q in A.caps.split(",")]:
    for p in range(A.pmin, A.pmax + 1):
        SR, best, perR = solve(opt, p, Q)
        plans = {"ROBUST": (SR, best, perR)}
        for t in PER:
            St = solve(opt[opt.period == t], p, Q)[0]
            plans[f"{t}-only"] = (St,) + solve(opt, p, Q, fix=St)[1:]
        for k, (S, v, per) in plans.items():
            rows.append(dict(Q=Q, p=p, plan=k, annual_k=round(v / 1000, 1), regret_pct=round(100 * (best - v) / best, 1),
                             **{f"{t}_k": round(per.get(t, 0) / 1000, 1) for t in PER}, sites=", ".join(name[i] for i in S)))
    R = pd.DataFrame([r for r in rows if r["Q"] == Q])
    print(f"\n=== capacity Q = {'none' if Q == 0 else int(Q)} passengers/hour per vertiport | scenario {A.scenario}, floor {A.floor} ===")
    print("Regret (% of yearly passengers lost vs robust):")
    print(R.pivot(index="p", columns="plan", values="regret_pct")[["ROBUST"] + [f"{t}-only" for t in PER]].to_string())
    print("Robust network, yearly passengers (thousands):")
    print(R[R.plan == "ROBUST"][["p", "annual_k"] + [f"{t}_k" for t in PER]].to_string(index=False))
    for r in R[(R.p == 6) & R.plan.isin(["ROBUST", "am-only", "pm-only"])].itertuples():
        print(f"  p=6 {r.plan:8s} {r.sites}")
os.makedirs(RES, exist_ok=True)
out = f"{RES}/p2cap_{A.scenario}_floor{A.floor}.csv"; pd.DataFrame(rows).to_csv(out, index=False); print("\nsaved", out)
