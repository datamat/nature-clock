"""Switzerland's nature clock.

Double-click to run. Reads every Google Trends CSV in ../01_Data_raw,
writes charts plus tables to ../03_Outputs.

File names in 01_Data_raw: <key>_<period>_<exportdate>.csv
  key    = first column of topics.csv, e.g. baerlauch
  period = 5y (weekly, past five years) or all (monthly, 2004 to today)
Example: baerlauch_5y_2026-11-10.csv
Each export holds the German, French plus Italian term in one request (see topics.csv).

Step 1 - annual cycle per topic: peak week, half-peak window, seasonality, dial.
Step 2 - shift: centre of each season per year (monthly 'all' exports),
         Theil-Sen trend in days per decade. Words peaking in December or
         January are left out: their season crosses the year end.
Step 3 - website: ../03_Outputs/website/index.html from website_template.html.
"""
import json
from datetime import date
import sys
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as e:
    print("Missing package:", e.name)
    print("Install once in a terminal:  pip install numpy pandas matplotlib")
    input("Press Enter to close.")
    sys.exit(1)

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "01_Data_raw"
OUT = HERE.parent / "03_Outputs"
SEASON_COLOUR = {"spring": "#5B8C3A", "summer": "#C9A227", "autumn": "#B5562B", "winter": "#3E6E8E", "year": "#7D8471"}
SEASON_ORDER = ["spring", "summer", "autumn", "winter", "year"]
MIN_RHYTHM_SHIFT = 0.5  # a word needs a season to track its shift
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# Google marks changes in its data collection on these dates (Trends chart notes).
DATA_BREAKS = [2011, 2016, 2022]
MIN_YEARS = 10  # good years needed for a trend
HEADER_WORDS = {"week", "month", "time", "date", "day", "woche", "monat", "zeit", "datum", "tag",
                "semaine", "mois", "temps", "jour", "settimana", "mese", "giorno"}


# ---------- reading ----------

def read_trends_csv(path):
    """Read a Google Trends CSV (old or new layout). Returns a Series indexed by date."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    start = next((i for i, l in enumerate(lines)
                  if l.split(",")[0].strip().strip('"').lower() in HEADER_WORDS), None)
    if start is None:
        raise ValueError("no Week/Month header line found")
    df = pd.read_csv(path, skiprows=start, encoding="utf-8-sig")
    # One request holds the German, French plus Italian term on one shared scale: sum them.
    vals = df.iloc[:, 1:].astype(str).apply(
        lambda c: pd.to_numeric(c.str.replace("<1", "0.5", regex=False), errors="coerce"))
    s = pd.Series(vals.sum(axis=1, min_count=1).values, index=pd.to_datetime(df.iloc[:, 0]))
    s = s.dropna().sort_index()
    # Drop the unfinished period at the end: the pull date sits in the file name.
    try:
        pulled = pd.Timestamp(path.stem.rsplit("_", 1)[-1])
        if "_all_" in path.name:
            s = s[s.index < pulled.replace(day=1)]
        else:
            s = s[s.index <= pulled - pd.Timedelta(days=7)]
    except ValueError:
        pass
    return s


def latest(files, key, period):
    mine = sorted(f for f in files if f.name.startswith(key + "_" + period + "_"))
    return mine[-1] if mine else None


# ---------- step 1: annual cycle ----------

def weekly_cycle(s):
    """Mean value per week of year (1-52), circularly smoothed over 3 weeks."""
    wk = s.index.isocalendar().week.clip(upper=52).values
    cyc = pd.Series(s.values).groupby(wk).mean().reindex(range(1, 53)).interpolate(limit_direction="both")
    v = cyc.values
    return (np.roll(v, 1) + v + np.roll(v, -1)) / 3


def monthly_cycle_as_weeks(s):
    """Mean per calendar month, spread to 52 weeks so both periods share one scale."""
    m = pd.Series(s.values).groupby(s.index.month).mean().reindex(range(1, 13))
    week_mid = np.arange(1, 53)
    month_of_week = np.clip(((week_mid - 0.5) / 52 * 12).astype(int) + 1, 1, 12)
    return m.loc[month_of_week].values


def season_window(cyc):
    """Peak week plus the circular window where the cycle stays above half its peak."""
    v = cyc - cyc.min()
    p = int(np.argmax(v))
    half = v[p] / 2
    lo = p
    while v[(lo - 1) % 52] >= half and (p - lo) < 51:
        lo -= 1
    hi = p
    while v[(hi + 1) % 52] >= half and (hi - lo) < 51:
        hi += 1
    width = hi - lo + 1
    contrast = (cyc.max() - cyc.min()) / cyc.max() if cyc.max() > 0 else 0
    return p + 1, (lo % 52) + 1, (hi % 52) + 1, width, contrast


def week_to_month(w):
    return MONTHS[min(11, int((w - 0.5) / 52 * 12))]


# ---------- step 2: spring shift ----------

def spring_months(s):
    """Months of the half-peak window of the monthly cycle, one month added each side."""
    m = pd.Series(s.values).groupby(s.index.month).mean().reindex(range(1, 13)).fillna(0).values
    v = m - m.min()
    p = int(np.argmax(v))
    lo = hi = p
    while lo > 0 and v[lo - 1] >= v[p] / 2:
        lo -= 1
    while hi < 11 and v[hi + 1] >= v[p] / 2:
        hi += 1
    return list(range(max(0, lo - 1) + 1, min(11, hi + 1) + 2))


def centre_of_mass_by_year(s, months):
    """Per year: search-weighted mean day of year over the spring months (complete years only)."""
    mid_doy = {m: (m - 0.5) * 365.25 / 12 for m in range(1, 13)}
    out = {}
    for year, g in s.groupby(s.index.year):
        g = g[g.index.month.isin(months)]
        g = g.groupby(g.index.month).mean()
        if len(g) < len(months) or (g.values <= 0).any():
            continue  # season incomplete, or months without measurable searches
        w = g.values - g.values.min()
        if w.sum() <= 0:
            continue
        out[year] = float(np.sum(w * np.array([mid_doy[m] for m in g.index])) / w.sum())
    return pd.Series(out)


def theil_sen(x, y):
    """Theil-Sen slope with its 95 % range (Sen 1968). Returns slope, lower, upper."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    if n < 5:
        return np.nan, np.nan, np.nan
    i, j = np.triu_indices(n, 1)
    slopes = np.sort((y[j] - y[i]) / (x[j] - x[i]))
    N = len(slopes)
    c = 1.96 * np.sqrt(n * (n - 1) * (2 * n + 5) / 18)
    lo = int(np.clip(np.round((N - c) / 2) - 1, 0, N - 1))
    hi = int(np.clip(np.round((N + c) / 2), 0, N - 1))
    return float(np.median(slopes)), float(slopes[lo]), float(slopes[hi])


def doy_label(d):
    return (pd.Timestamp("2001-01-01") + pd.Timedelta(days=float(d) - 1)).strftime("%d %b")


# ---------- main ----------

def main():
    OUT.mkdir(exist_ok=True)
    topics = pd.read_csv(HERE / "topics.csv", sep=";", keep_default_na=False)
    files = sorted(RAW.glob("*.csv"))
    if not files:
        print("No CSV files in", RAW)
        input("Press Enter to close.")
        return

    rows, cycles, shift_rows, com_years, monthly = [], {}, [], {}, {}
    for t in topics.itertuples():
        f5, fall = latest(files, t.key, "5y"), latest(files, t.key, "all")
        src = f5 or fall
        if src is None:
            continue
        try:
            s = read_trends_csv(src)
        except Exception as e:
            print(f"{t.de}: could not read {src.name} ({e})")
            continue
        if (s > 0).mean() < 0.5:
            print(f"{t.de}: over 50 % zeros, dropped")
            continue
        cyc = weekly_cycle(s) if f5 else monthly_cycle_as_weeks(s)
        peak, start, end, width, contrast = season_window(cyc)
        cycles[t.key] = cyc
        rows.append(dict(key=t.key, topic=t.de, season=t.season, source=src.name,
                         peak_week=peak, peak_month=week_to_month(peak),
                         start_week=start, end_week=end, weeks_above_half=width,
                         seasonality=round(contrast, 2)))

        if fall is not None:
            monthly[t.key] = read_trends_csv(fall)
        # Step 2 for every topic whose season does not cross the year end
        if fall is not None and week_to_month(peak) not in ("Dec", "Jan") and contrast >= MIN_RHYTHM_SHIFT:
            sa = monthly[t.key]
            months = spring_months(sa)
            com = centre_of_mass_by_year(sa, months)
            if len(com) >= MIN_YEARS:
                com_years[t.key] = (t.de, com, t.season)
                b, lo, hi = theil_sen(com.index, com.values)
                late = com[com.index >= 2016]
                b16 = theil_sen(late.index, late.values)[0] if len(late) >= 5 else np.nan
                shift_rows.append(dict(
                    key=t.key, topic=t.de, source=fall.name,
                    months=f"{MONTHS[months[0]-1]}-{MONTHS[months[-1]-1]}",
                    first_year=int(com.index.min()), last_year=int(com.index.max()), years=len(com),
                    mean_centre=doy_label(com.mean()),
                    days_per_decade=round(b * 10, 1),
                    ci95_low=round(lo * 10, 1), ci95_high=round(hi * 10, 1),
                    significant="yes" if (hi < 0 or lo > 0) else "no",
                    days_per_decade_since_2016=round(b16 * 10, 1)))

    res = pd.DataFrame(rows)
    if res.empty:
        print("No usable topics.")
        input("Press Enter to close.")
        return
    res["season_rank"] = res.season.map(SEASON_ORDER.index)
    res = res.sort_values(["season_rank", "peak_week"]).drop(columns="season_rank")
    res.to_csv(OUT / "nature_clock_summary.csv", sep=";", index=False)
    draw_cycles(res, cycles)
    draw_dial(res)
    print("STEP 1 - annual cycle")
    print(res[["topic", "peak_month", "peak_week", "weeks_above_half", "seasonality"]].to_string(index=False))

    if shift_rows:
        sh = pd.DataFrame(shift_rows)
        sh.to_csv(OUT / "nature_clock_shift.csv", sep=";", index=False)
        pd.DataFrame({v[0]: v[1] for v in com_years.values()}).round(1).rename_axis("year").to_csv(
            OUT / "nature_clock_shift_by_year.csv", sep=";")
        draw_shift(com_years, sh)
        print("\nSTEP 2 - shift of each season (negative = earlier)")
        print(sh[["topic", "months", "years", "mean_centre", "days_per_decade",
                  "ci95_low", "ci95_high", "significant"]].to_string(index=False))
    else:
        sh = pd.DataFrame()
        print("\nSTEP 2 skipped: needs '_all_' exports.")

    build_website(res, cycles, monthly, sh, com_years, topics)

    print("\nOutputs written to", OUT)
    input("Press Enter to close.")


# ---------- charts ----------

def plain(ax):
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


def draw_cycles(res, cycles):
    n = len(res)
    cols = min(5, n)
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(2.6 * cols, 1.9 * rows), sharex=True, squeeze=False)
    weeks = np.arange(1, 53)
    for ax, r in zip(axes.flat, res.itertuples()):
        c = cycles[r.key]
        col = SEASON_COLOUR[r.season]
        ax.plot(weeks, c / c.max() * 100, color=col, lw=1.8)
        ax.axvline(r.peak_week, color=col, lw=0.8, ls=":")
        ax.set_title(r.topic, fontsize=9, loc="left")
        ax.set_ylim(0, 105)
        ax.set_xticks([1, 14, 27, 40])
        ax.set_xticklabels(["Jan", "Apr", "Jul", "Oct"], fontsize=7)
        ax.tick_params(axis="y", labelsize=7)
        plain(ax)
    for ax in list(axes.flat)[n:]:
        ax.axis("off")
    fig.suptitle("Annual cycle of search interest, Switzerland (share of each topic's own peak)",
                 fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"nature_clock_cycles.{ext}", dpi=200)
    plt.close(fig)


def draw_dial(res):
    fig = plt.figure(figsize=(7, 7))
    ax = fig.add_subplot(projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    to_theta = lambda w: (w - 1) / 52 * 2 * np.pi
    n = len(res)
    for i, r in enumerate(res.itertuples()):
        radius = 6.0 + i
        col = SEASON_COLOUR[r.season]
        end = r.end_week if r.end_week >= r.start_week else r.end_week + 52
        th = np.linspace(to_theta(r.start_week), to_theta(end + 1), 60)
        ax.plot(th, np.full_like(th, radius), color=col, lw=6, solid_capstyle="round")
        ax.plot([to_theta(r.peak_week + 0.5)], [radius], "o", color="white", ms=3.5, zorder=3)
        ax.text(to_theta(r.peak_week + 0.5), radius + 0.5, r.topic, fontsize=6.5, ha="center",
                va="center", color="#222",
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.8))
    ax.set_xticks([to_theta(1 + k * 52 / 12) for k in range(12)])
    ax.set_xticklabels([])
    for k, m in enumerate(MONTHS):
        ax.text(to_theta(1 + (k + 0.5) * 52 / 12), n + 7.3, m, fontsize=9, ha="center",
                va="center", color="#444")
    ax.set_yticks([])
    ax.set_ylim(0, n + 7.6)
    ax.spines["polar"].set_visible(False)
    ax.grid(color="#ddd", lw=0.6)
    ax.set_title("Switzerland's nature clock\nArcs: weeks above half of each topic's peak · dot: peak week",
                 fontsize=10, pad=18)
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"nature_clock_dial.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)


def draw_shift(com_years, sh):
    n = len(com_years)
    cols = min(3, n)
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(3.4 * cols, 2.4 * rows), sharex=True, squeeze=False)
    for ax, (key, (name, com, season)), r in zip(axes.flat, com_years.items(), sh.itertuples()):
        col = SEASON_COLOUR[season]
        x, y = com.index.values.astype(float), com.values
        ax.plot(x, y, "o", color=col, ms=3.5)
        b = r.days_per_decade / 10
        a = np.median(y - b * x)
        ax.plot(x, a + b * x, color="#333", lw=1)
        for br in DATA_BREAKS:
            ax.axvline(br, color="#bbb", lw=0.6, ls=":")
        ticks = np.linspace(y.min(), y.max(), 3)
        ax.set_yticks(ticks)
        ax.set_yticklabels([doy_label(t) for t in ticks], fontsize=7)
        ax.tick_params(axis="x", labelsize=7)
        ax.set_title(f"{name}: {r.days_per_decade:+.1f} days per decade", fontsize=9, loc="left")
        plain(ax)
    for ax in list(axes.flat)[n:]:
        ax.axis("off")
    fig.suptitle("Centre of each season's search interest per year, Switzerland (Theil-Sen trend; dotted: Google data breaks)",
                 fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(OUT / f"nature_clock_shift.{ext}", dpi=200)
    plt.close(fig)


# ---------- step 3: website ----------

def build_website(res, cycles, monthly, sh, com_years, topics):
    tpl = HERE / "website_template.html"
    if not tpl.exists():
        return
    meta = topics.set_index("key")
    shift = {r.key: r for r in sh.itertuples()} if len(sh) else {}
    items, starts, ends = [], [], []
    for r in res.itertuples():
        c = cycles[r.key]
        t = dict(key=r.key, de=r.topic, fr=str(meta.at[r.key, "fr"] or ""), it=str(meta.at[r.key, "it"] or ""),
                 season=r.season, volume=float(meta.at[r.key, "volume"]) if "volume" in meta else 0.0,
                 peak_week=int(r.peak_week), start_week=int(r.start_week), end_week=int(r.end_week),
                 weeks_above_half=int(r.weeks_above_half), seasonality=float(r.seasonality),
                 cycle=[round(float(v) / c.max() * 100, 1) for v in c], monthly=None, shift=None)
        if r.key in monthly:
            m = monthly[r.key].resample("MS").mean()
            m = m / m.max() * 100
            t["monthly"] = dict(start=m.index[0].strftime("%Y-%m"),
                                values=[None if pd.isna(v) else round(float(v), 1) for v in m.values])
            starts.append(m.index[0]); ends.append(m.index[-1])
        if r.key in shift:
            s = shift[r.key]
            t["shift"] = dict(days_per_decade=float(s.days_per_decade), ci95_low=float(s.ci95_low),
                              ci95_high=float(s.ci95_high), significant=s.significant == "yes",
                              years={str(int(y)): round(float(d), 1) for y, d in com_years[r.key][1].items()})
        items.append(t)
    cand_file = OUT / "nature_clock_candidates.csv"
    cands = []
    if cand_file.exists():
        cd = pd.read_csv(cand_file, sep=";", keep_default_na=False)
        cands = [dict(key=c.key, de=c.de, volume=float(c.volume), reason=c.reason) for c in cd.itertuples()]
    weekly_dates = [read_trends_csv(f).index for f in sorted(RAW.glob("*_5y_*.csv"))[:1]]
    p5 = [f"{weekly_dates[0][0]:%Y-%m}", f"{weekly_dates[0][-1]:%Y-%m}"] if weekly_dates else None
    pall = [f"{min(starts):%Y-%m}", f"{max(ends):%Y-%m}"] if starts else None
    pulled = max(f.stem.rsplit("_", 1)[-1] for f in RAW.glob("*_5y_*.csv"))
    data = dict(topics=items, candidates=cands, period_5y=p5, period_all=pall, pulled=pulled,
                built=date.today().isoformat(), breaks=DATA_BREAKS)
    html = tpl.read_text(encoding="utf-8").replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False))
    site = OUT / "website"
    site.mkdir(exist_ok=True)
    (site / "index.html").write_text(html, encoding="utf-8")
    print("Website written to", site / "index.html")


if __name__ == "__main__":
    main()
