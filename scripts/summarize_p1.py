import glob, re, sys, pandas as pd
RES = sys.argv[1] if len(sys.argv) > 1 else "results"
rows = []
for f in sorted(glob.glob(f"{RES}/p1_*_x_*_floor0.15.csv")):
    s, per = re.search(r"p1_(.+)_x_(.+)_floor", f).groups()
    R = pd.read_csv(f).set_index("p")
    at = lambda p, c: R[c].get(p, float("nan"))
    err6 = 100 * (at(6, "uni_forecast") - at(6, "pax_uni_net")) / at(6, "pax_uni_net")
    rows.append(dict(scenario=s, period=per, pax_p4=at(4, "pax_het"), pax_p6=at(6, "pax_het"), pax_p10=at(10, "pax_het"),
                     VOH_p4=at(4, "VOH_pct"), VOH_p6=at(6, "VOH_pct"), VOH_max=R.VOH_pct.max(), p_at_max=R.VOH_pct.idxmax(),
                     min_jaccard=R.jaccard.min(), uni_forecast_err_p6=round(err6, 1)))
T = pd.DataFrame(rows)
order = {"launch": 0, "adopter": 1, "mature": 2}
T = T.sort_values(["scenario", "period"], key=lambda c: c.map(order) if c.name == "scenario" else c)
print("RQ1 grid, exact shares, saving floor 0.15 (VOH in % of passengers; forecast error = pooled model vs truth on its own network)\n")
print(T.to_string(index=False))
T.to_csv(f"{RES}/rq1_grid_summary.csv", index=False); print(f"\nsaved {RES}/rq1_grid_summary.csv")
