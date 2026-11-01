import numpy as np
import pandas as pd

df = pd.read_csv("data/raw/chicago/tnp_od_period_2026-03.csv")
df["minutes"] = df.sec_mean / 60

# 1. O'Hare direction by period (trips per day)
oh = df[(df.o == 76) ^ (df.d == 76)].copy()
oh["direction"] = np.where(oh.o == 76, "from O'Hare", "to O'Hare")
print("O'Hare trips per day, by direction and period:")
print(oh.pivot_table(index="period", columns="direction", values="trips_per_day", aggfunc="sum").round(0).to_string())

# 2. Long trips (>= 20 min) by period
long = df[df.minutes >= 20].copy()
tot = df.groupby("period").trips_per_day.sum()
lng = long.groupby("period").trips_per_day.sum()
print("\nShare of trips that are >= 20 min, by period:")
print((lng / tot).round(3).to_string())
for p in ["am", "pm", "weekend"]:
    top = long[long.period == p].nlargest(8, "trips_per_day")
    print(f"\nTop long OD pairs, {p} (community area numbers):")
    print(top[["o", "d", "trips_per_day", "minutes", "price_mean"]].round(1).to_string(index=False))

# 3. First look at RQ1: mu_od and sigma_od under three scenarios
# Air fare P = base + rate * straight-line miles; straight line ~ road miles / 1.25 (rough, for this first look only)
SCEN = {"launch": (15, 6.0, 62.0), "base": (15, 4.5, 21.8), "mature": (15, 2.5, 21.8)}
long["straight_miles"] = long.miles_mean / 1.25
for name, (base, rate, vot) in SCEN.items():
    b = vot / 60                       # $ per minute
    P = base + rate * long.straight_miles
    mu = (P * long.inv_t - long.q_over_t) / b
    e2 = (P**2 * long.inv_t2 - 2 * P * long.q_over_t2 + long.q2_over_t2) / b**2
    sig = np.sqrt(np.clip(e2 - mu**2, 0, None))
    long[f"mu_{name}"], long[f"sig_{name}"] = mu, sig
    w = long.trips_per_day
    print(f"\nScenario {name} (${base} + ${rate}/mile, VOT ${vot}/h), long trips, all periods:")
    print(f"  demand-weighted median mu = {np.average(mu, weights=w):.2f} (weighted mean), "
          f"share of demand with mu < 0.4: {w[mu < 0.4].sum() / w.sum():.1%}, "
          f"mu < 0.6: {w[mu < 0.6].sum() / w.sum():.1%}, mu < 1: {w[mu < 1].sum() / w.sum():.1%}")
    ohl = long[(long.o == 76) | (long.d == 76)]
    print(f"  O'Hare long trips: weighted mean mu = {np.average(ohl[f'mu_{name}'], weights=ohl.trips_per_day):.2f}, "
          f"mean sigma = {np.average(ohl[f'sig_{name}'], weights=ohl.trips_per_day):.2f}")
long.to_csv("data/processed/chicago_long_od_mu_first_look.csv", index=False)
print("\nsaved data/processed/chicago_long_od_mu_first_look.csv")
