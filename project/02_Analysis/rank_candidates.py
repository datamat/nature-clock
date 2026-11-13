"""Nature clock - pick the top 20 words.

Double-click to run. Reads the ranking pull in ../01_Data_raw/ranking
(every candidate from candidates.csv, past five years, weekly, pulled together
with the German word "Pilze" as a fixed reference), then:
  volume       mean search interest relative to "Pilze" (= 100)
  rhythm       seasonality of the average year: (max - min) / max
  zero share   share of weeks without measurable searches
Top 20 = highest volume among words with a clear yearly rhythm.
Words marked force = yes in candidates.csv are always kept (e.g. the wolf).
A word with a Google topic id in the topic column is pulled as that topic.
Writes topics.csv (the 20 words) plus ../03_Outputs/nature_clock_candidates.csv.
"""
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "01_Data_raw" / "ranking"
OUT = HERE.parent / "03_Outputs"
TOP_N = 20
MIN_RHYTHM = 0.6      # clear yearly rhythm
MAX_ZERO_SHARE = 0.5  # enough search volume
YEAR_ROUND = 0.4      # below this rhythm a word counts as searched all year


def season_of(week, rhythm=1.0):
    if rhythm < YEAR_ROUND:
        return "year"
    month = pd.Timestamp("2025-01-01") + pd.Timedelta(days=(week - 1) * 7 + 3)
    m = month.month
    return "spring" if 3 <= m <= 5 else "summer" if 6 <= m <= 8 else "autumn" if 9 <= m <= 11 else "winter"


def cycle(values, dates):
    wk = pd.DatetimeIndex(dates).isocalendar().week.clip(upper=52).values
    cyc = pd.Series(values).groupby(wk).mean().reindex(range(1, 53)).interpolate(limit_direction="both").values
    return (np.roll(cyc, 1) + cyc + np.roll(cyc, -1)) / 3


def main():
    OUT.mkdir(exist_ok=True)
    files = sorted(RAW.glob("ranking_5y_*.csv"))
    if not files:
        print("No ranking file in", RAW)
        input("Press Enter to close.")
        return
    # every ranking file counts; a later file wins for the same word
    df = pd.concat([pd.read_csv(f, sep=";", parse_dates=["week"], encoding="utf-8-sig") for f in files])
    df = df.drop_duplicates(["key", "week"], keep="last")
    df = df[df.partial == 0]
    cand = pd.read_csv(HERE / "candidates.csv", sep=";", keep_default_na=False)
    rows = []
    for c in cand.itertuples():
        d = df[df.key == c.key]
        if d.empty:
            continue
        vol = d.topic.mean() / d.anchor.mean() * 100
        cyc = cycle(d.topic.values, d.week.values)
        rhythm = (cyc.max() - cyc.min()) / cyc.max() if cyc.max() > 0 else 0
        zero = (d.topic == 0).mean()
        peak = int(np.argmax(cyc)) + 1
        rows.append(dict(key=c.key, group=c.group, de=c.de, fr=c.fr, it=c.it, topic=c.topic, force=c.force,
                         volume=round(vol, 2), rhythm=round(rhythm, 2), zero_share=round(zero, 2),
                         peak_week=peak, season=season_of(peak, rhythm)))
    r = pd.DataFrame(rows).sort_values("volume", ascending=False).reset_index(drop=True)
    forced = r.force == "yes"
    ok = (r.rhythm >= MIN_RHYTHM) & (r.zero_share <= MAX_ZERO_SHARE) & ~forced
    chosen = list(r[ok].head(TOP_N).key) + list(r[forced].key)
    r["selected"] = r.key.isin(chosen)
    r["reason"] = np.where(forced, "added by hand", np.where(r.selected, "selected",
                  np.where(r.zero_share > MAX_ZERO_SHARE, "too little search volume",
                  np.where(r.rhythm < MIN_RHYTHM, "no clear yearly rhythm", "outside the top 20 by volume"))))
    r.to_csv(OUT / "nature_clock_candidates.csv", sep=";", index=False)
    top = r[r.selected][["key", "season", "group", "volume", "de", "fr", "it", "topic"]]
    top.to_csv(HERE / "topics.csv", sep=";", index=False)
    print(r[["de", "volume", "rhythm", "zero_share", "peak_week", "reason"]].to_string(index=False))
    print(f"\n{len(top)} words written to topics.csv")
    input("Press Enter to close.")


if __name__ == "__main__":
    main()
