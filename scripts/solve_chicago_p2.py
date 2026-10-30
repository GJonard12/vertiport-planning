import argparse, os, pickle, pandas as pd
import gurobipy as gp
from gurobipy import GRB

ap = argparse.ArgumentParser()
ap.add_argument("--scenario", default="adopter")
ap.add_argument("--floor", type=float, default=0.15)
ap.add_argument("--pmin", type=int, default=2)
ap.add_argument("--pmax", type=int, default=8)
ap.add_argument("--weekdays", type=int, default=250)
ap.add_argument("--weekend_days", type=int, default=115)
A = ap.parse_args()

I = pickle.load(open("data/processed/chicago_instance.pkl", "rb"))
od, opt, cdf = I["od"], I["options"].copy(), I["candidates"]
name = dict(zip(cdf.zone, cdf.name)); V = cdf.zone.tolist()
col = f"x_het_{A.scenario}"                                   # OD-specific exact shares = truth
opt = opt[(opt.saving >= A.floor) & (opt[col] > 0)].reset_index(drop=True)
W = {"am": A.weekdays, "midday": A.weekdays, "pm": A.weekdays, "other": A.weekdays, "weekend": A.weekend_days}
PER = list(W)
opt["val"] = opt[col] * od.loc[opt.od_row, "trips_per_day"].values * opt.period.map(W).values   # passengers per year

def solve(sub, p):                       # Model P2 (all periods share y); P1 when sub holds one period
    sub = sub.reset_index(drop=True)
    m = gp.Model(); m.Params.OutputFlag = 0
    y = m.addVars(V, vtype=GRB.BINARY); x = m.addVars(len(sub), ub=1.0)
    m.setObjective(gp.quicksum(sub.val.iat[k] * x[k] for k in range(len(sub))), GRB.MAXIMIZE)
    for r, g in sub.groupby("od_row").groups.items():
        m.addConstr(gp.quicksum(x[k] for k in g) <= 1)
        for i, gi in sub.loc[g].groupby("i").groups.items():
            m.addConstr(gp.quicksum(x[k] for k in gi) <= y[i])
        for j, gj in sub.loc[g].groupby("j").groups.items():
            m.addConstr(gp.quicksum(x[k] for k in gj) <= y[j])
    m.addConstr(y.sum() <= p); m.optimize()
    return [i for i in V if y[i].X > 0.5]

def annual(S, per=None):                 # Proposition 1 closed form, passengers per year
    ok = opt.i.isin(S) & opt.j.isin(S) & (opt.period == per if per else True)
    return float(opt.loc[ok].groupby("od_row").val.max().sum())

rows = []
for p in range(A.pmin, A.pmax + 1):
    plans = {"ROBUST": solve(opt, p)}
    for t in PER:
        plans[f"{t}-only"] = solve(opt[opt.period == t], p)
    best = annual(plans["ROBUST"])
    for k, S in plans.items():
        v = annual(S)
        rows.append(dict(p=p, plan=k, annual_k=round(v / 1000, 1), regret_pct=round(100 * (best - v) / best, 1),
                         jaccard=round(len(set(S) & set(plans["ROBUST"])) / len(set(S) | set(plans["ROBUST"])), 2),
                         **{f"{t}_k": round(annual(S, t) / 1000, 1) for t in PER},
                         sites=", ".join(name[i] for i in S)))
R = pd.DataFrame(rows)
print(f"RQ2, scenario {A.scenario}, exact OD-specific shares, floor {A.floor}, "
      f"{A.weekdays} weekdays + {A.weekend_days} weekend days per year")
print("\nRegret (% of yearly passengers lost vs the robust network) of planning for one period only:")
print(R.pivot(index="p", columns="plan", values="regret_pct")[["ROBUST"] + [f"{t}-only" for t in PER]].to_string())
print("\nJaccard similarity with the robust network:")
print(R.pivot(index="p", columns="plan", values="jaccard")[["ROBUST"] + [f"{t}-only" for t in PER]].to_string())
print("\nRobust network: yearly passengers (thousands), total and by period:")
print(R[R.plan == "ROBUST"][["p", "annual_k"] + [f"{t}_k" for t in PER]].to_string(index=False))
for p in sorted({min(4, A.pmax), min(6, A.pmax)}):
    print(f"\nSites at p = {p}:")
    for r in R[R.p == p].itertuples():
        print(f"  {r.plan:15s} {r.sites}")
os.makedirs("results", exist_ok=True)
out = f"results/p2_{A.scenario}_floor{A.floor}.csv"; R.to_csv(out, index=False); print("\nsaved", out)
