import argparse, pickle, numpy as np, pandas as pd
import gurobipy as gp
from gurobipy import GRB

ap = argparse.ArgumentParser()
ap.add_argument("--scenario", default="adopter")
ap.add_argument("--share", default="x", choices=["x", "a"])     # x = exact, a = paper's DRO
ap.add_argument("--period", default="weekday")                  # am, midday, pm, other, weekend, weekday
ap.add_argument("--floor", type=float, default=0.15)            # minimum relative time saving
ap.add_argument("--pmax", type=int, default=10)
A = ap.parse_args()

I = pickle.load(open("data/processed/chicago_instance.pkl", "rb"))
od, opt, cdf = I["od"], I["options"].copy(), I["candidates"]
name = dict(zip(cdf.zone, cdf.name))
pers = ["am", "midday", "pm", "other"] if A.period == "weekday" else [A.period]
opt = opt[opt.period.isin(pers) & (opt.saving >= A.floor)].reset_index(drop=True)
opt["D"] = od.loc[opt.od_row, "trips_per_day"].values
het, uni = f"{A.share}_het_{A.scenario}", f"{A.share}_uni_{A.scenario}"
opt = opt[(opt[het] > 0) | (opt[uni] > 0)].reset_index(drop=True)
V = cdf.zone.tolist()
print(f"scenario {A.scenario}, share {'exact' if A.share == 'x' else 'DRO'}, period {A.period}, "
      f"saving floor {A.floor}: {opt.od_row.nunique()} OD x period, {len(opt)} options")

def evaluate(S, col):            # Proposition 1: best open option per OD, closed form
    ok = opt.i.isin(S) & opt.j.isin(S)
    return float((opt.loc[ok, col] * opt.loc[ok, "D"]).groupby(opt.loc[ok, "od_row"]).max().sum())

def solve(col, p):
    m = gp.Model(); m.Params.OutputFlag = 0
    y = m.addVars(V, vtype=GRB.BINARY)
    x = m.addVars(len(opt), ub=1.0)
    m.setObjective(gp.quicksum(opt[col].iat[k] * opt.D.iat[k] * x[k] for k in range(len(opt))), GRB.MAXIMIZE)
    for r, g in opt.groupby("od_row").groups.items():
        m.addConstr(gp.quicksum(x[k] for k in g) <= 1)
        for i, gi in opt.loc[g].groupby("i").groups.items():
            m.addConstr(gp.quicksum(x[k] for k in gi) <= y[i])
        for j, gj in opt.loc[g].groupby("j").groups.items():
            m.addConstr(gp.quicksum(x[k] for k in gj) <= y[j])
    m.addConstr(y.sum() <= p)
    m.optimize()
    return [i for i in V if y[i].X > 0.5], m.ObjVal, m.Runtime

rows = []
for p in range(1, A.pmax + 1):
    Sh, vh, th = solve(het, p)
    Su, vu, tu = solve(uni, p)
    truth_u = evaluate(Su, het)
    jac = len(set(Sh) & set(Su)) / len(set(Sh) | set(Su))
    rows.append(dict(p=p, pax_het=round(vh), pax_uni_net=round(truth_u), VOH_pct=round(100 * (vh - truth_u) / vh, 1) if vh else 0,
                     uni_forecast=round(vu), jaccard=round(jac, 2), sec=round(th + tu, 1),
                     sites_het=", ".join(name[i] for i in Sh), sites_uni=", ".join(name[i] for i in Su)))
R = pd.DataFrame(rows)
print("\npax_het = passengers/day of the best network under OD-specific shares (truth)")
print("pax_uni_net = same truth, network chosen with pooled shares; VOH_pct = loss from planning with the average")
print("uni_forecast = what the pooled model predicted for its own network\n")
print(R.drop(columns=["sites_het", "sites_uni"]).to_string(index=False))
print("\nSites chosen:")
for r in R.itertuples():
    print(f" p={r.p:2d}  het: {r.sites_het}\n       uni: {r.sites_uni}")
out = f"results/p1_{A.scenario}_{A.share}_{A.period}_floor{A.floor}.csv"
import os; os.makedirs("results", exist_ok=True); R.to_csv(out, index=False); print("\nsaved", out)
