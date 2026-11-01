"""Static figures for the Chicago vertiport study (adopter scenario unless stated).
Writes figures/fig1_network_map.png, fig2_rq2_regret.png, fig3_capacity.png, fig4_rq1_forecast.png"""
import os, pickle, numpy as np, pandas as pd, geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

os.makedirs("figures", exist_ok=True)
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#fcfcfb"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True,
                     "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF})

I = pickle.load(open("data/processed/chicago_instance.pkl", "rb"))
od, opt, cdf = I["od"], I["options"], I["candidates"]
zones = gpd.read_file("data/raw/chicago/community_areas.geojson").to_crs(4326)
pos = {r.zone: (r.lon, r.lat) for r in cdf.itertuples()}
zone_of = dict(zip(cdf.name, cdf.zone))
DAYS = {"am": 250, "midday": 250, "pm": 250, "other": 250, "weekend": 115}
SC, FLOOR = "adopter", 0.15

def flows(sites, periods=None):
    """Passengers per year on each vertiport pair when the network `sites` is open (best option per OD x period)."""
    o = opt[(opt.saving >= FLOOR) & opt.i.isin(sites) & opt.j.isin(sites)]
    if periods: o = o[o.period.isin(periods)]
    o = o.assign(v=o[f"x_het_{SC}"] * od.loc[o.od_row, "trips_per_day"].values * o.period.map(DAYS).values)
    o = o.loc[o.groupby("od_row").v.idxmax()]
    o = o.assign(a=o[["i", "j"]].min(axis=1), b=o[["i", "j"]].max(axis=1))
    return o.groupby(["a", "b"]).v.sum().sort_values(ascending=False)

def sites_of(df, plan, p):
    return [zone_of[s] for s in df[(df.plan == plan) & (df.p == p)].sites.iloc[0].split(", ")]

# ---------- Figure 1: robust 6-vertiport network and its air corridors ----------
P2 = pd.read_csv("results/p2_adopter_floor0.15.csv")
S = sites_of(P2, "ROBUST", 6)
F = flows(S)
fig, ax = plt.subplots(figsize=(7.2, 9))
zones.plot(ax=ax, color="#efeeea", edgecolor="white", linewidth=0.8)
for (a, b), v in F.items():
    if v < 2000: continue
    (x1, y1), (x2, y2) = pos[a], pos[b]
    ax.plot([x1, x2], [y1, y2], color=BLUE, lw=0.6 + 9 * v / F.max(), alpha=0.75, solid_capstyle="round", zorder=2)
others = [z for z in cdf.zone if z not in S]
ax.scatter([pos[z][0] for z in others], [pos[z][1] for z in others], s=40, facecolor=SURF, edgecolor=MUTED, lw=1.2, zorder=3)
thr = {z: F[[k for k in F.index if z in k]].sum() for z in S}
for z in S:
    ax.scatter(*pos[z], s=60 + 900 * thr[z] / max(thr.values()), color=BLUE, edgecolor="white", lw=2, zorder=4)
    name = cdf.set_index("zone").name[z]
    left = z in (76, 28)                                   # O'Hare and Vertiport Chicago labelled on the left
    ax.annotate(f"{name}\n{thr[z]/1000:.0f}k pax/yr", pos[z], xytext=(-16 if left else 16, -10 if z == 28 else 0),
                textcoords="offset points", ha="right" if left else "left", va="center", fontsize=8.5, color=INK, zorder=5)
ax.set_axis_off()
ax.set_title("Robust 6-vertiport network, Chicago (adopter scenario)", loc="left", fontsize=12, color=INK, pad=42)
ax.text(0, 1.01, f"{F.sum()/1000:.0f}k air-taxi passengers per year. Line width = passengers per vertiport pair;\n"
        "label = passengers departing or arriving at the vertiport.",
        transform=ax.transAxes, fontsize=9, color=INK2, va="bottom")
ax.legend(handles=[Line2D([], [], marker="o", ls="", color=BLUE, ms=9, label="selected vertiport"),
                   Line2D([], [], marker="o", ls="", mfc=SURF, mec=MUTED, ms=7, label="other candidate"),
                   Line2D([], [], color=BLUE, lw=4, alpha=0.75, label="air corridor")],
          loc="lower left", frameon=False, fontsize=9)
fig.savefig("figures/fig1_network_map.png", dpi=200, bbox_inches="tight"); plt.close(fig)
print("fig1:", [cdf.set_index("zone").name[z] for z in S], f"{F.sum()/1000:.0f}k pax/yr")

# ---------- Figure 2: RQ2 regret of single-period plans, three scenarios ----------
PLANS = [("am-only", "AM-peak plan", BLUE), ("pm-only", "PM-peak plan", ORANGE), ("midday-only", "Midday plan", AQUA)]
fig, axs = plt.subplots(1, 3, figsize=(11, 3.8), sharey=True)
for ax, sc in zip(axs, ["launch", "adopter", "mature"]):
    R = pd.read_csv(f"results/p2_{sc}_floor0.15.csv")
    for plan, lab, col in PLANS:
        r = R[R.plan == plan].sort_values("p")
        ax.plot(r.p, r.regret_pct, color=col, lw=2, marker="o", ms=5, mec="white", mew=1, label=lab)
    ax.set_title(f"{sc} scenario", loc="left", fontsize=10, color=INK)
    ax.set_xlabel("number of vertiports p"); ax.grid(axis="y", color=GRID, lw=0.8); ax.set_xticks(range(2, 9))
axs[0].set_ylabel("yearly passengers lost vs robust network (%)")
axs[0].legend(frameon=False, fontsize=9, loc="upper left")
fig.suptitle("RQ2: designing for one time period loses passengers; the midday plan stays close to the robust network",
             x=0.01, ha="left", fontsize=11.5, color=INK)
fig.tight_layout(); fig.savefig("figures/fig2_rq2_regret.png", dpi=200); plt.close(fig)

# ---------- Figure 3: capacity ----------
C = pd.read_csv("results/p2cap_adopter_floor0.15.csv")
QS = [(0, "no limit"), (200, "200 pax/h"), (100, "100 pax/h"), (50, "50 pax/h")]
fig, axs = plt.subplots(1, 2, figsize=(11, 4), gridspec_kw={"width_ratios": [1.3, 1]})
ax = axs[0]
x = np.arange(len(QS)); w = 0.26
for k, (plan, lab, col) in enumerate(PLANS):
    vals = [C[(C.Q == q) & (C.plan == plan) & C.p.between(4, 7)].regret_pct.max() for q, _ in QS]
    b = ax.bar(x + (k - 1) * w, vals, w - 0.03, color=col, label=lab)
    ax.bar_label(b, fmt="%.0f", fontsize=8, color=INK2, padding=2)
ax.set_xticks(x, [l for _, l in QS]); ax.set_xlabel("vertiport capacity (departing + arriving passengers per hour)")
ax.set_ylabel("worst regret at p = 4-7 (%)"); ax.grid(axis="y", color=GRID, lw=0.8); ax.legend(frameon=False, fontsize=9)
ax.set_title("Tighter capacity mostly shrinks regret", loc="left", fontsize=10, color=INK)
ax = axs[1]
rob = C[(C.plan == "ROBUST") & (C.p == 6)].set_index("Q")
PER = [("am_k", "AM 7-10", BLUE), ("midday_k", "midday 10-16", AQUA), ("pm_k", "PM 16-19", ORANGE)]
bottom = np.zeros(len(QS))
for colname, lab, col in PER:
    v = np.array([rob.loc[q, colname] for q, _ in QS])
    ax.bar(x, v, 0.6, bottom=bottom, color=col, label=lab, edgecolor=SURF, lw=2); bottom += v
rest = np.array([rob.loc[q, "annual_k"] for q, _ in QS]) - bottom
ax.bar(x, rest, 0.6, bottom=bottom, color="#c9c8c3", label="evening + weekend", edgecolor=SURF, lw=2)
for xi, tot in zip(x, bottom + rest): ax.text(xi, tot + 12, f"{tot:.0f}k", ha="center", fontsize=8.5, color=INK2)
ax.set_xticks(x, [l for _, l in QS]); ax.set_ylabel("yearly passengers, p = 6 (thousands)")
ax.grid(axis="y", color=GRID, lw=0.8); ax.legend(frameon=False, fontsize=8.5, loc="upper right")
ax.set_title("Capacity cuts the market, mostly in the PM peak", loc="left", fontsize=10, color=INK)
fig.tight_layout(); fig.savefig("figures/fig3_capacity.png", dpi=200); plt.close(fig)

# ---------- Figure 4: RQ1, what the average-customer model gets wrong ----------
G = pd.read_csv("results/rq1_grid_summary.csv")
PERIODS = [("am", "AM"), ("midday", "midday"), ("pm", "PM"), ("weekend", "weekend")]
SCS = [("launch", BLUE), ("adopter", ORANGE), ("mature", AQUA)]
fig, axs = plt.subplots(1, 2, figsize=(11, 4))
x = np.arange(len(PERIODS)); w = 0.26
for ax, colname, ttl, yl in [(axs[0], "uni_forecast_err_p6", "Forecast error of the average-customer model (p = 6)",
                              "predicted minus actual passengers (%)"),
                             (axs[1], "VOH_max", "Value of heterogeneity (VOH): network planned with the average",
                              "passengers lost (%, worst p)")]:
    for k, (sc, col) in enumerate(SCS):
        v = [G[(G.scenario == sc) & (G.period == p)][colname].iloc[0] for p, _ in PERIODS]
        b = ax.bar(x + (k - 1) * w, v, w - 0.03, color=col, label=sc)
        ax.bar_label(b, fmt="%.0f", fontsize=7.5, color=INK2, padding=2)
    ax.axhline(0, color=MUTED, lw=1); ax.set_xticks(x, [l for _, l in PERIODS]); ax.set_ylabel(yl)
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_title(ttl, loc="left", fontsize=10, color=INK)
axs[0].legend(frameon=False, fontsize=9, title="scenario", title_fontsize=9, loc="upper left")
axs[1].text(0.02, 0.97, "launch weekend: 30% of only ~17 passengers/day", transform=axs[1].transAxes, ha="left",
            va="top", fontsize=8, color=INK2)
fig.tight_layout(); fig.savefig("figures/fig4_rq1_forecast.png", dpi=200); plt.close(fig)
print("saved figures/fig1-fig4")
