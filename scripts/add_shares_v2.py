import pickle, numpy as np, pandas as pd
F = "data/processed/chicago_instance.pkl"
I = pickle.load(open(F, "rb"))
od, opt, cfg, cdf = I["od"], I["options"], I["cfg"], I["candidates"]
zn = dict(zip(I["zones"].ca_num, I["zones"].ca_name)); cn = dict(zip(cdf.zone, cdf.name))
w = od.trips_per_day.to_numpy()
SHRINK_N, SDX_FLOOR = 30, 0.01                    # prior strength (trips), floor on sd of X ($/min)
sl = np.sqrt(np.log(1 + cfg["vot_cv"] ** 2))
zk, wk = np.polynomial.hermite.hermgauss(24)       # Gauss-Hermite over log VOT
zk, wk = np.sqrt(2) * zk, wk / np.sqrt(np.pi)

def Phi(x):                                        # standard normal cdf (Abramowitz-Stegun 7.1.26)
    z = np.abs(x) / np.sqrt(2); t = 1 / (1 + 0.3275911 * z)
    y = 1 - t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429)))) * np.exp(-z * z)
    return 0.5 * (1 + np.sign(x) * y)

def exact(sv, EX, sdX, bmed):                      # P(X / b <= sv), X normal, b lognormal
    b = bmed * np.exp(sl * zk)                     # quadrature nodes for VOT
    return (wk * Phi((np.multiply.outer(sv, b) - EX[..., None]) / sdX[..., None])).sum(-1)

def dro(sv, mu, sig):
    tt = (sv - mu) / sig
    return np.where(tt > 0, tt ** 2 / (1 + tt ** 2), 0.0)

grid = np.linspace(0, 1, 201)
rows = opt.od_row.to_numpy()
for s, sc in cfg["scenarios"].items():
    bmed = sc["vot"] / 60
    P = od[f"P_{s}"]
    EX = (P * od.inv_t - od.q_over_t).to_numpy()                       # $ per minute saved, mean
    VX = (P**2 * od.inv_t2 - 2*P*od.q_over_t2 + od.q2_over_t2).to_numpy() - EX**2 - (2.5**2/12) * od.inv_t2.to_numpy()
    sdX = np.sqrt(np.clip(VX, 0, None))
    prior = od.assign(sdX=sdX).groupby("period").sdX.median()          # shrink thin ODs to period median
    n = od.n.to_numpy()
    sdX = np.maximum((n * sdX + SHRINK_N * od.period.map(prior).to_numpy()) / (n + SHRINK_N), SDX_FLOOR)
    od[f"EX_{s}"], od[f"sdX_{s}"] = EX, sdX
    mu, sig = od[f"mu_{s}"].to_numpy(), od[f"sig_{s}"].to_numpy()
    mub = np.average(mu, weights=w); sigb = np.sqrt(np.average(sig**2 + mu**2, weights=w) - mub**2)
    opt[f"a_het_{s}"] = dro(opt.saving.to_numpy(), mu[rows], sig[rows])
    opt[f"a_uni_{s}"] = dro(opt.saving.to_numpy(), mub, sigb)
    opt[f"x_het_{s}"] = exact(opt.saving.to_numpy(), EX[rows], sdX[rows], bmed)
    pooled = np.array([np.average(exact(np.full(len(EX), g), EX, sdX, bmed), weights=w) for g in grid])
    opt[f"x_uni_{s}"] = np.interp(opt.saving.to_numpy(), grid, pooled)
    od[f"mu_bar_{s}"], od[f"sig_bar_{s}"] = mub, sigb
    print(f"{s:12s} pooled mu = {mub:5.2f}, pooled sigma = {sigb:5.2f}; exact pooled share at saving 0.3 / 0.5: {np.interp(.3, grid, pooled):.3f} / {np.interp(.5, grid, pooled):.3f}")

print("\nUpper bound passengers per day (all candidates open, best option per OD x period)")
print("dro = paper's worst-case share, exact = lognormal VOT x normal trip conditions; het = OD-specific, uni = pooled")
for s in cfg["scenarios"]:
    tab = {}
    for k in ["a_het", "a_uni", "x_het", "x_uni"]:
        best = opt.groupby("od_row")[f"{k}_{s}"].max()
        tab[k.replace("a_", "dro_").replace("x_", "exact_")] = (best * od.loc[best.index, "trips_per_day"]).groupby(od.loc[best.index, "period"]).sum()
    t = pd.DataFrame(tab).fillna(0); t.loc["WEEKDAY total"] = t.drop("weekend", errors="ignore").sum()
    print(f"\n[{s}]"); print(t.round(0).to_string())

best = opt.loc[opt.groupby("od_row").x_het_adopter.idxmax()]
best = best.assign(pax=best.x_het_adopter * od.loc[best.od_row, "trips_per_day"].values).nlargest(15, "pax")
for c in ["o", "d", "i", "j"]:
    best[c] = best[c].map(zn if c in "od" else cn)
print("\nTop 15 OD x period, adopter, exact OD-specific share:")
print(best[["period", "o", "d", "i", "j", "tau", "saving", "x_het_adopter", "x_uni_adopter", "pax"]].round(2).to_string(index=False))
I["od"], I["options"] = od, opt
pickle.dump(I, open(F, "wb"))
print("\nupdated", F)
