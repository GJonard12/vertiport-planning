"""Sensitivity to a fixed transfer ("hassle") penalty h added to air-taxi trip time (16 sites, March 2026).
Usage: python scripts/hassle_sensitivity.py        -> results/hassle_sensitivity.csv, figures/fig6_hassle.png"""
import sys, numpy as np, pandas as pd
import matplotlib.pyplot as plt
sys.argv = sys.argv[:1]
sys.path.insert(0, "scripts")
import bootstrap_days as bd                               # same build rules and exact evaluation

HS, FLOORS = [0, 5, 10, 15], [0.15, 0.0]                  # hassle minutes; minimum saving (0 = hassle replaces floor)
name = dict(zip(bd.cdf.zone, bd.cdf.name))
df = bd.aggregate(bd.wkd, bd.wke)
rows = []
for h in HS:
    od, opt = bd.build(df, hassle=h)
    for f in FLOORS:
        bd.FLOOR = f
        for r in bd.analyse(opt): rows.append(dict(hassle=h, floor=f, **r))
R = pd.DataFrame(rows)
R["peak_regret"] = R[["regret_am", "regret_pm"]].max(axis=1)
R.to_csv("results/hassle_sensitivity.csv", index=False)

# Summary per scenario: p = 6 passengers and network, worst peak / midday regret over p = 4-8
for f in FLOORS:
    print(f"\n=== minimum saving {f:.2f} ===")
    for s in ["launch", "adopter", "mature"]:
        g = R[(R.floor == f) & (R.scenario == s)]
        ref = set(g[(g.hassle == 0) & (g.p == 6)].robust.iloc[0])
        print(f"[{s}]")
        for h in HS:
            a = g[g.hassle == h]; r6 = a[a.p == 6].iloc[0]; band = a[a.p.between(4, 8)]
            jac = len(ref & set(r6.robust)) / len(ref | set(r6.robust))
            print(f"  h={h:2d} min: pax p6 {r6.annual_k:6.0f}k | same p6 sites as h=0: {jac:4.2f} | worst peak regret "
                  f"{band.peak_regret.max():4.1f}% | worst midday {band.regret_midday.max():4.1f}% | fcst err p6 {r6.fcst_err_weekday:5.1f}%")
        print("   p6 sites at h=15:", ", ".join(name[z] for z in g[(g.hassle == 15) & (g.p == 6)].robust.iloc[0]))

# Figure (minimum saving 0.15)
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#fcfcfb"
COL = {"launch": "#2a78d6", "adopter": "#eb6834", "mature": "#1baf7a"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.axisbelow": True, "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF})
fig, axs = plt.subplots(1, 4, figsize=(15, 3.9))
G = R[(R.floor == 0.15) & (R.p == 6)]
pick = lambda s, h, c: G[(G.scenario == s) & (G.hassle == h)][c].iloc[0]
def lines(ax, series, ttl, yl=None):
    for lab, c, fn in series:
        ax.plot(HS, [fn(h) for h in HS], color=c, lw=2, marker="o", ms=5, mec="white", mew=1, label=lab)
    ax.set_title(ttl, loc="left", fontsize=10, color=INK); ax.set_xticks(HS); ax.set_xlabel("hassle penalty h (minutes)")
    ax.grid(axis="y", color=GRID, lw=0.8); ax.legend(frameon=False, fontsize=8.5)
lines(axs[0], [(s, c, lambda h, s=s: pick(s, h, "annual_k")) for s, c in COL.items()], "Yearly passengers (thousands)")
lines(axs[1], [(s, c, lambda h, s=s: 100 * pick(s, h, "pm_k") / pick(s, h, "annual_k")) for s, c in COL.items()],
      "Share of passengers in the PM peak (%)")
PL = [("AM-peak plan", "#2a78d6", "regret_am"), ("PM-peak plan", "#eb6834", "regret_pm"), ("Midday plan", "#1baf7a", "regret_midday")]
lines(axs[2], [(l, c, lambda h, k=k: pick("adopter", h, k)) for l, c, k in PL], "Regret of single-period plans, adopter (%)")
lines(axs[3], [(s, c, lambda h, s=s: pick(s, h, "fcst_err_weekday")) for s, c in COL.items()], "Average-customer forecast error (%)")
axs[3].axhline(0, color=MUTED, lw=1)
fig.suptitle("Sensitivity to a fixed transfer penalty: robust network with 6 vertiports, minimum saving 15%", x=0.01, ha="left", fontsize=11.5, color=INK)
fig.tight_layout(); fig.savefig("figures/fig6_hassle.png", dpi=200); print("\nsaved results/hassle_sensitivity.csv, figures/fig6_hassle.png")
