import pathlib, pickle
import pandas as pd
import gurobipy as gp
from gurobipy import GRB

P = pathlib.Path("data/processed")
inst = pickle.load(open(P / "nyc_instance.pkl", "rb"))
opt = inst["options"].reset_index(drop=True)
cand = inst["candidates"]
name = pd.read_csv(P / "nyc_zone_centroids.csv").set_index("LocationID").zone.to_dict()

# Model: y_i = 1 if vertiport i is built; x_k = share of OD demand sent through option k = (o, d, i, j)
m = gp.Model("vertiport_pmax")
m.Params.OutputFlag = 0
y = m.addVars(cand, vtype=GRB.BINARY, name="y")
x = m.addVars(len(opt), lb=0, ub=1, name="x")
w = (opt.D * opt.share).to_numpy()            # passengers if option k carries all of its OD pair
m.setObjective(gp.quicksum(w[k] * x[k] for k in range(len(opt))), GRB.MAXIMIZE)

for _, g in opt.groupby(["o", "d"]):           # each OD pair is assigned at most once
    m.addConstr(gp.quicksum(x[k] for k in g.index) <= 1)
for (o, d, i), g in opt.groupby(["o", "d", "i"]):   # only use departure vertiport i if built
    m.addConstr(gp.quicksum(x[k] for k in g.index) <= y[i])
for (o, d, j), g in opt.groupby(["o", "d", "j"]):   # only use arrival vertiport j if built
    m.addConstr(gp.quicksum(x[k] for k in g.index) <= y[j])
card = m.addConstr(y.sum() <= 2)              # at most p vertiports (changed in the loop)

rows, prev = [], set()
for p in range(2, 11):
    card.RHS = p
    m.optimize()
    built = {i for i in cand if y[i].X > 0.5}
    rows.append(dict(p=p, passengers=round(m.ObjVal, 1),
                     added=", ".join(sorted(name[i] for i in built - prev)),
                     removed=", ".join(sorted(name[i] for i in prev - built)) or "-"))
    if p == 3:
        flows = [(name[opt.o[k]], name[opt.d[k]], name[opt.i[k]], name[opt.j[k]], round(w[k] * x[k].X, 1))
                 for k in range(len(opt)) if x[k].X > 1e-6]
        top3 = sorted(flows, key=lambda r: -r[4])[:8]
    prev = built

res = pd.DataFrame(rows)
print("Max air-taxi passengers (weekday 7-10 am) with at most p vertiports:\n")
print(res.to_string(index=False))
print("\nLargest flows when p = 3 (origin, destination, departure vertiport, arrival vertiport, passengers):")
for r in top3:
    print("  ", r)
res.to_csv(P / "nyc_pmax_results.csv", index=False)
