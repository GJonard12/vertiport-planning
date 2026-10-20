import pathlib, pickle
import numpy as np
import pandas as pd
import gurobipy as gp
from gurobipy import GRB

P = pathlib.Path("data/processed")
inst = pickle.load(open(P / "nyc_instance.pkl", "rb"))
cfg, cand = inst["cfg"], inst["candidates"]
opt = inst["options"].reset_index(drop=True)
name = pd.read_csv(P / "nyc_zone_centroids.csv").set_index("LocationID").zone.to_dict()
D, S, sigma = opt.D.to_numpy(), opt.saving.to_numpy(), cfg["sigma"]

# Paper, Table 4: vertiports built for each mu (Astoria = Rainey Park, approximated by the Astoria zone)
base = ["JFK Airport", "Clinton East", "Astoria"]
PAPER = {0.40: base, 0.39: base, 0.38: base,
         0.37: base + ["Clinton West"], 0.36: base + ["Clinton West"],
         0.35: base + ["Clinton West", "Midtown Center", "Garment District", "Lincoln Square East"],
         0.34: base + ["Clinton West", "Midtown Center", "Garment District", "TriBeCa/Civic Center",
                       "Upper West Side South", "Gramercy"],
         0.33: base + ["Clinton West", "Midtown Center", "Garment District", "TriBeCa/Civic Center",
                       "Upper West Side South", "Gramercy", "Newark Airport"]}

def shares(mu):
    tt = (S - mu) / sigma
    return np.where(tt > 0, tt**2 / (1 + tt**2), 0.0)

# Model structure (built once; only objective coefficients change)
m = gp.Model("vertiport_fixed_cost")
m.Params.OutputFlag = 0
m.ModelSense = GRB.MAXIMIZE
y = m.addVars(cand, vtype=GRB.BINARY, name="y")
x = m.addVars(len(opt), lb=0, ub=1, name="x")
for _, g in opt.groupby(["o", "d"]):
    m.addConstr(gp.quicksum(x[k] for k in g.index) <= 1)
for (o, d, i), g in opt.groupby(["o", "d", "i"]):
    m.addConstr(gp.quicksum(x[k] for k in g.index) <= y[i])
for (o, d, j), g in opt.groupby(["o", "d", "j"]):
    m.addConstr(gp.quicksum(x[k] for k in g.index) <= y[j])
xs, ys = [x[k] for k in range(len(opt))], [y[i] for i in cand]

def solve(mu, c):
    w = D * shares(mu)
    m.setAttr("Obj", xs, w.tolist())
    m.setAttr("Obj", ys, [-c] * len(ys))
    m.optimize()
    built = sorted(name[i] for i in cand if y[i].X > 0.5)
    pax = float(sum(w[k] * xs[k].X for k in range(len(xs))))
    return built, pax

# 1. Calibrate c: number of vertiports at mu = 0.40 for a range of costs
grid = np.arange(0.5, 60.5, 0.5)
counts = [len(solve(0.40, c)[0]) for c in grid]
print("Vertiports built at mu = 0.40 as the cost per vertiport c increases:")
last = None
for c, n in zip(grid, counts):
    if n != last:
        print(f"  c >= {c:5.1f}  ->  {n} vertiports")
        last = n
ok = [c for c, n in zip(grid, counts) if n == 3]
if ok:
    c_star = (min(ok) + max(ok)) / 2
    print(f"c gives 3 vertiports for c in [{min(ok)}, {max(ok)}]; using the midpoint c = {c_star}")
else:
    c_star = grid[int(np.argmin([abs(n - 3) for n in counts]))]
    print(f"WARNING: no c gives exactly 3 vertiports; using c = {c_star}")

# 2. Sweep mu with c fixed, compare with the paper
rows, prev = [], set()
for mu in [0.40, 0.39, 0.38, 0.37, 0.36, 0.35, 0.34, 0.33]:
    built, pax = solve(mu, c_star)
    b, pp = set(built), set(PAPER[mu])
    rows.append(dict(mu=mu, n_ours=len(b), n_paper=len(pp), passengers=round(pax, 1),
                     same_as_paper=len(b & pp),
                     added=", ".join(sorted(b - prev)) or "-",
                     removed=", ".join(sorted(prev - b)) or "-"))
    prev = b
res = pd.DataFrame(rows)
print("\nmu sweep with fixed cost c (paper's Table 4 counts in n_paper):\n")
print(res.to_string(index=False))
print("\nOur network at mu = 0.40:", ", ".join(solve(0.40, c_star)[0]))
print("Our network at mu = 0.33:", ", ".join(solve(0.33, c_star)[0]))
res.to_csv(P / "nyc_mu_sweep_results.csv", index=False)
