"""Animated 'week in Chicago' for the robust 6-vertiport network (adopter scenario).
Illustration of the model's period averages, not a flight simulation.
Writes figures/chicago_week.gif (and .mp4 if ffmpeg is available)."""
import os, shutil, textwrap, pickle, numpy as np, pandas as pd, geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter, FFMpegWriter

INK, INK2, MUTED, SURF, BLUE, ORANGE = "#0b0b0b", "#52514e", "#8a8984", "#fcfcfb", "#2a78d6", "#eb6834"
plt.rcParams.update({"font.family": "DejaVu Sans", "figure.facecolor": SURF, "axes.facecolor": SURF})
SC, FLOOR, P, PAX_PER_DOT, FPS = "adopter", 0.15, 6, 4, 12
PERIODS = [("am", "Weekday 7:00\u201310:00", "AM peak", 3, 250), ("midday", "Weekday 10:00\u201316:00", "Midday", 6, 250),
           ("pm", "Weekday 16:00\u201319:00", "PM peak", 3, 250), ("other", "Weekday 19:00\u20137:00", "Evening and night", 12, 250),
           ("weekend", "Saturday and Sunday", "Weekend", 24, 115)]
HOLD, BLEND = 40, 10                                    # frames per period, frames of transition

I = pickle.load(open("data/processed/chicago_instance.pkl", "rb"))
od, opt, cdf = I["od"], I["options"], I["candidates"]
zones = gpd.read_file("data/raw/chicago/community_areas.geojson").to_crs(4326)
pos = {r.zone: np.array([r.lon, r.lat]) for r in cdf.itertuples()}
zname = dict(zip(cdf.zone, cdf.name)); zone_of = dict(zip(cdf.name, cdf.zone))
P2 = pd.read_csv("results/p2_adopter_floor0.15.csv")
plan = lambda k: [zone_of[s] for s in P2[(P2.plan == k) & (P2.p == P)].sites.iloc[0].split(", ")]
S = plan("ROBUST")

def hourly(t, hours):                                    # passengers per hour on each directed vertiport pair
    o = opt[(opt.period == t) & (opt.saving >= FLOOR) & opt.i.isin(S) & opt.j.isin(S)]
    o = o.assign(v=o[f"x_het_{SC}"] * od.loc[o.od_row, "trips_per_day"].values / hours)
    o = o.loc[o.groupby("od_row").v.idxmax()]
    return o.groupby(["i", "j"]).v.sum()

pairs = sorted({(i, j) for i in S for j in S if i != j})
RATE = np.array([[hourly(t, h).get(pr, 0.0) for pr in pairs] for t, _, _, h, _ in PERIODS])   # periods x pairs
THRU = np.array([[sum(RATE[k, n] for n, pr in enumerate(pairs) if z in pr) for z in S] for k in range(len(PERIODS))])
REG = {t: P2[(P2.plan == f"{t}-only") & (P2.p == P)].regret_pct.iloc[0] for t, *_ in PERIODS}
ALT = {t: plan(f"{t}-only") for t, *_ in PERIODS}
print("passengers per hour by period:", dict(zip([p[0] for p in PERIODS], RATE.sum(1).round(0))))

# ---------- drawing ----------
fig = plt.figure(figsize=(7.2, 8.4), dpi=100)
ax = fig.add_axes([0.0, 0.19, 1.0, 0.66]); ax.set_axis_off()
zones.plot(ax=ax, color="#efeeea", edgecolor="white", linewidth=0.7)
ax.set_xlim(-87.96, -87.50); ax.set_ylim(41.64, 42.03); ax.set_aspect(1 / np.cos(np.radians(41.85)))
others = [z for z in cdf.zone if z not in S]
ax.scatter([pos[z][0] for z in others], [pos[z][1] for z in others], s=30, facecolor=SURF, edgecolor=MUTED, lw=1, zorder=2)
for i, j in pairs:
    if i < j: ax.plot(*zip(pos[i], pos[j]), color=BLUE, lw=0.8, alpha=0.25, zorder=2)
hubs = ax.scatter([pos[z][0] for z in S], [pos[z][1] for z in S], s=80, color=BLUE, edgecolor="white", lw=1.5, zorder=4)
alt = ax.scatter([], [], s=260, facecolor="none", edgecolor=ORANGE, lw=2, zorder=5)
dots = ax.scatter([], [], s=10, color="#1f3f6b", zorder=6)
hub_lab = []
for z in S:
    left = z in (76, 28)
    hub_lab.append(ax.annotate(zname[z], pos[z], xytext=(-10 if left else 10, -9 if z == 28 else 0), textcoords="offset points",
                ha="right" if left else "left", va="center", fontsize=8, color=INK, zorder=7))
others_named = {z: zname[z] for z in cdf.zone if z not in S}
alt_lab = [ax.annotate("", pos[z], xytext=(9, 6), textcoords="offset points", fontsize=7.5, color=ORANGE, zorder=7)
           for z in others_named]

fig.text(0.04, 0.965, "A week of air-taxi demand on Chicago's robust 6-vertiport network", fontsize=12, color=INK)
fig.text(0.04, 0.94, "Adopter scenario (\\$15 + \\$3.50/mile), March 2026 rideshare data", fontsize=9, color=INK2)
t_title = fig.text(0.04, 0.895, "", fontsize=15, color=INK, weight="bold")
t_sub = fig.text(0.04, 0.868, "", fontsize=10, color=INK2)
t_note = fig.text(0.04, 0.843, "", fontsize=9, color=INK2, style="italic")
t_rate = fig.text(0.96, 0.895, "", fontsize=15, color=BLUE, ha="right", weight="bold")
fig.text(0.96, 0.868, "air-taxi passengers per hour", fontsize=9, color=INK2, ha="right")
t_alt = fig.text(0.04, 0.122, "", fontsize=9, color=ORANGE, va="top", linespacing=1.4)
fig.text(0.04, 0.02, f"Illustration of the model's period averages (demand spread evenly within each period), not a flight "
         f"simulation.\nEach dot = about {PAX_PER_DOT} passengers per hour. Dot size of vertiports = passengers per hour "
         "departing or arriving.", fontsize=7.5, color=MUTED)
bar = fig.add_axes([0.04, 0.165, 0.92, 0.012]); bar.set_axis_off(); bar.set_xlim(0, len(PERIODS)); bar.set_ylim(0, 1)
cells = [bar.add_patch(plt.Rectangle((k + 0.03, 0), 0.94, 1, color="#dddcd7")) for k in range(len(PERIODS))]
for k, p in enumerate(PERIODS): bar.text(k + 0.5, -1.4, p[2], ha="center", va="top", fontsize=7.5, color=INK2)

N = len(PERIODS) * HOLD
rng = np.random.default_rng(0)
phase0 = rng.random((len(pairs), 200))
seg = np.array([[pos[i], pos[j]] for i, j in pairs])     # pairs x 2 x 2
LEN = np.hypot(*(seg[:, 1] - seg[:, 0]).T); SPEED = 1 / (30 * LEN / np.median(LEN))   # same speed on every corridor
def state(f):                                            # period index and blend weight toward the next period
    k, r = divmod(f, HOLD); w = max(0, (r - (HOLD - BLEND)) / BLEND)
    return k, (k + 1) % len(PERIODS), w

def draw(f):
    k, k2, w = state(f)
    rate = (1 - w) * RATE[k] + w * RATE[k2]; thru = (1 - w) * THRU[k] + w * THRU[k2]
    pts = []
    for n, r in enumerate(rate):
        m = int(round(r / PAX_PER_DOT))
        if m == 0: continue
        s = (phase0[n, :m] + f * SPEED[n]) % 1.0         # constant speed: long corridors take longer
        pts.append(seg[n, 0] + s[:, None] * (seg[n, 1] - seg[n, 0]))
    dots.set_offsets(np.vstack(pts) if pts else np.empty((0, 2)))
    sizes = 40 + 1600 * thru / THRU.max(); hubs.set_sizes(sizes)
    for lab, sz, z in zip(hub_lab, sizes, S):                # keep each label just outside its circle
        gap = np.sqrt(sz) / 2 + 4; lab.xyann = (-gap if z in (76, 28) else gap, -9 if z == 28 else 0)
    t, sub, name, h, d = PERIODS[k if w < 0.5 else k2]
    t_title.set_text(name); t_rate.set_text(f"{rate.sum():.0f}")
    t_sub.set_text(sub); t_note.set_text("Roads are fast, so almost no trip saves 15% by flying." if rate.sum() < 10 else "")
    extra = [z for z in ALT[t] if z not in S]; dropped = [z for z in S if z not in ALT[t]]
    alt.set_offsets(np.array([pos[z] for z in extra]) if extra else np.empty((0, 2)))
    for lab, z in zip(alt_lab, others_named): lab.set_text(zname[z] if z in extra else "")
    if extra or dropped:
        t_alt.set_text(textwrap.fill(f"Orange rings: a network planned for this period alone would build "
                       f"{', '.join(zname[z] for z in extra)} instead of {', '.join(zname[z] for z in dropped)}, "
                       f"and would lose {REG[t]:.0f}% of yearly passengers compared with the robust network.", 100))
    else:
        t_alt.set_text(f"A network planned for this period alone is the same as the robust network\n(loss {REG[t]:.0f}% of yearly passengers).")
    for c, cell in enumerate(cells): cell.set_color(BLUE if c == (k if w < 0.5 else k2) else "#dddcd7")
    return [dots, hubs, alt, t_title, t_sub, t_rate, t_alt, *alt_lab, *hub_lab, *cells, t_note]

anim = FuncAnimation(fig, draw, frames=N, interval=1000 / FPS, blit=False)
os.makedirs("figures", exist_ok=True)
anim.save("figures/chicago_week.gif", writer=PillowWriter(fps=FPS)); print("saved figures/chicago_week.gif")
if shutil.which("ffmpeg"):
    anim.save("figures/chicago_week.mp4", writer=FFMpegWriter(fps=FPS, bitrate=2500), dpi=150)
    print("saved figures/chicago_week.mp4")
else:
    print("ffmpeg not found: skipped the .mp4 (install with: conda install -c conda-forge ffmpeg)")
for k in range(len(PERIODS)):                            # one still per period, for checking and for the write-up
    draw(k * HOLD + HOLD // 2); fig.savefig(f"figures/week_frame_{PERIODS[k][0]}.png", dpi=100)
