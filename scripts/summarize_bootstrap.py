"""Summarize results/bootstrap_samples.csv: intervals, network stability, and figures/fig5_bootstrap.png."""
import pickle, numpy as np, pandas as pd
import matplotlib.pyplot as plt

R = pd.read_csv("results/bootstrap_samples.csv")
cdf = pickle.load(open("data/processed/chicago_instance.pkl", "rb"))["candidates"]
name = dict(zip(cdf.zone.astype(str), cdf.name))
base, boot = R[R["sample"] == 0].set_index(["scenario", "p"]), R[R["sample"] > 0]
B = boot["sample"].nunique()
lo, hi = (lambda x: np.percentile(x, 5)), (lambda x: np.percentile(x, 95))
fmt = lambda b, l, h: f"{b:5.1f} [{l:5.1f}, {h:5.1f}]"

print(f"Day-level bootstrap, {B} samples (22 weekdays and 9 weekend days resampled with replacement)")
print("Format: original month [5th, 95th percentile across samples]\n")
rows = []
for (s, p), g in boot.groupby(["scenario", "p"], sort=False):
    b0 = base.loc[(s, p)]
    rows.append({"scenario": s, "p": p,
                 "pax_k_per_yr": fmt(b0.annual_k, lo(g.annual_k), hi(g.annual_k)),
                 "same_robust_net_%": round(100 * (g.robust == b0.robust).mean()),
                 "regret_AM": fmt(b0.regret_am, lo(g.regret_am), hi(g.regret_am)),
                 "regret_PM": fmt(b0.regret_pm, lo(g.regret_pm), hi(g.regret_pm)),
                 "regret_midday": fmt(b0.regret_midday, lo(g.regret_midday), hi(g.regret_midday)),
                 "midday<5%_%": round(100 * (g.regret_midday < 5).mean()),
                 "VOH_wkday": fmt(b0.VOH_weekday, lo(g.VOH_weekday), hi(g.VOH_weekday)),
                 "fcst_err_wkday": fmt(b0.fcst_err_weekday, lo(g.fcst_err_weekday), hi(g.fcst_err_weekday))})
T = pd.DataFrame(rows)
order = {"launch": 0, "adopter": 1, "mature": 2}
T = T.sort_values(["scenario", "p"], key=lambda c: c.map(order) if c.name == "scenario" else c)
pd.set_option("display.width", 250)
for s in ["launch", "adopter", "mature"]:
    print(f"[{s}]"); print(T[T.scenario == s].drop(columns="scenario").to_string(index=False)); print()
T.to_csv("results/bootstrap_summary.csv", index=False)

# Worst single-peak regret at p = 4..8, per sample: how often is planning for one peak costly?
print("Share of samples in which the worst single-peak plan (AM or PM, p = 4-8) loses more than 10%, and midday stays below 5%:")
for s in ["launch", "adopter", "mature"]:
    g = boot[(boot.scenario == s) & boot.p.between(4, 8)].groupby("sample")
    peak = g.apply(lambda d: max(d.regret_am.max(), d.regret_pm.max()))
    mid = g.regret_midday.max()
    print(f"  {s:8s} peak > 10%: {100 * (peak > 10).mean():5.1f}%   midday < 5% at every p: {100 * (mid < 5).mean():5.1f}%")

# Site inclusion frequency in the robust network
print("\nHow often each site is in the robust network (adopter):")
inc = {}
for p in (4, 6):
    sets = boot[(boot.scenario == "adopter") & (boot.p == p)].robust.str.split("-")
    inc[p] = pd.Series([z for s in sets for z in s]).value_counts() / len(sets) * 100
I = pd.DataFrame(inc).fillna(0).rename(index=name).sort_values(6, ascending=False)
print(I.round(0).astype(int).rename(columns={4: "p=4 (%)", 6: "p=6 (%)"}).to_string())

# ---------- figure ----------
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#fcfcfb"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.axisbelow": True, "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF})
fig = plt.figure(figsize=(12.5, 4.3))
gs = fig.add_gridspec(1, 4, width_ratios=[1, 1, 1, 1.5], wspace=0.12)
A = boot[boot.scenario == "adopter"]; A0 = base.loc["adopter"]; ax0 = None
for k, (col, lab, c) in enumerate([("regret_am", "AM-peak plan", BLUE), ("regret_pm", "PM-peak plan", ORANGE),
                                   ("regret_midday", "Midday plan", AQUA)]):
    ax = fig.add_subplot(gs[k], sharey=ax0); ax0 = ax0 or ax
    q = A.groupby("p")[col].quantile([0.05, 0.25, 0.75, 0.95]).unstack()
    ax.fill_between(q.index, q[0.05], q[0.95], color=c, alpha=0.15, lw=0, label="90% of samples")
    ax.fill_between(q.index, q[0.25], q[0.75], color=c, alpha=0.30, lw=0, label="middle 50%")
    ax.plot(A0.index, A0[col], color=c, lw=2, marker="o", ms=5, mec="white", mew=1, label="March 2026")
    ax.set_title(lab, loc="left", fontsize=10, color=INK); ax.set_xticks(range(2, 9)); ax.set_xlabel("vertiports p")
    ax.grid(axis="y", color=GRID, lw=0.8)
    if k == 0: ax.set_ylabel("yearly passengers lost vs robust network (%)"); ax.legend(frameon=False, fontsize=8, loc="upper right")
    else: plt.setp(ax.get_yticklabels(), visible=False)
ax = fig.add_subplot(gs[3]); I = I.sort_values([6, 4], ascending=False)
y = np.arange(len(I))
ax.barh(y - 0.2, I[4], 0.38, color="#9cc2ee", label="p = 4"); ax.barh(y + 0.2, I[6], 0.38, color=BLUE, label="p = 6")
ax.set_yticks(y, I.index); ax.yaxis.tick_right(); ax.invert_yaxis(); ax.set_xlim(0, 105)
ax.set_xlabel("share of bootstrap samples (%)"); ax.grid(axis="x", color=GRID, lw=0.8)
ax.legend(frameon=False, fontsize=9, loc="lower right")
ax.set_title("Sites in the robust network", loc="left", fontsize=10, color=INK)
fig.suptitle(f"Day-level bootstrap ({B} resamples of March 2026 days), adopter scenario", x=0.01, ha="left", fontsize=11.5, color=INK)
fig.subplots_adjust(left=0.06, right=0.88, bottom=0.15, top=0.83)
fig.savefig("figures/fig5_bootstrap.png", dpi=200); print("\nsaved figures/fig5_bootstrap.png")
