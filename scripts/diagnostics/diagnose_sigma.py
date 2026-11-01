import pickle, numpy as np, pandas as pd
I = pickle.load(open("data/processed/chicago_instance.pkl", "rb"))
od, cfg = I["od"], I["cfg"]
zn = dict(zip(I["zones"].ca_num, I["zones"].ca_name))
w = od.trips_per_day
od["r1"] = od.inv_t * od.minutes          # about 1.0-1.1 if trip times are clean
od["r2"] = od.inv_t2 * od.minutes ** 2    # about 1.0-1.3 if trip times are clean
print("Jensen ratios (clean data: r1 about 1.0-1.1, r2 about 1.0-1.3)")
print(od[["r1", "r2"]].describe(percentiles=[.1, .5, .9, .99]).round(2).to_string())
print(f"share of trips in OD x period with r2 > 2: {w[od.r2 > 2].sum() / w.sum():.1%}")

s = "adopter"; b = cfg["scenarios"][s]["vot"] / 60; P = od[f"P_{s}"]
mu0 = (P * od.inv_t - od.q_over_t) / b
v0 = (P**2 * od.inv_t2 - 2*P*od.q_over_t2 + od.q2_over_t2) / b**2 - mu0**2 - (2.5**2/12) * od.inv_t2 / b**2
od["sig0"] = np.sqrt(np.clip(v0, 0, None))   # sigma from trip conditions only (one VOT)
print("\nadopter: 10th / 50th / 90th percentile and trip-weighted mean")
for c in [f"mu_{s}", f"sig_{s}", "sig0"]:
    q = np.percentile(od[c], [10, 50, 90])
    print(f"  {c:12s} {q[0]:6.2f} {q[1]:6.2f} {q[2]:6.2f}   mean {np.average(od[c], weights=w):6.2f}")
print("correlation between r2 and sigma:", round(np.corrcoef(od.r2, od[f"sig_{s}"])[0, 1], 2))

t = od.nlargest(10, f"sig_{s}").copy()
t["o"], t["d"] = t.o.map(zn), t.d.map(zn)
print("\nTop 10 OD x period by sigma (adopter):")
print(t[["period", "o", "d", "n", "minutes", "price_mean", "r1", "r2", f"mu_{s}", f"sig_{s}", "sig0"]].round(2).to_string(index=False))
