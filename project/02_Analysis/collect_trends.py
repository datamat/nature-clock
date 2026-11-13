"""Nature clock - data collector.

Double-click to run. For every topic in topics.csv it pulls two Google Trends
series for Switzerland and saves them unchanged to ../01_Data_raw:
  <key>_5y_<date>.csv   past five years, weekly
  <key>_all_<date>.csv  2004 to today, monthly
One request per topic: the German, French plus Italian term together.
Files already pulled today are skipped, so a rerun after an error resumes.

Google limits how fast it answers. The script waits between requests and
pauses for a minute when Google says "too many requests". If it keeps failing,
run it again later, or use the export links in the project.
"""
import csv
import json
import random
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "01_Data_raw"
BASE = "https://trends.google.com"
PERIODS = {"5y": ("today 5-y", "Week", "%Y-%m-%d"), "all": ("all", "Month", "%Y-%m")}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
opener.addheaders = [("User-Agent", UA), ("Accept-Language", "de-CH,de;q=0.9")]


def get_json(path, params):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    for attempt in range(6):
        try:
            with opener.open(url, timeout=30) as r:
                txt = r.read().decode("utf-8")
            return json.loads(txt[txt.index("{"):])
        except urllib.error.HTTPError as e:
            wait = 60 if e.code == 429 else 10
            print(f"   Google answered {e.code}, waiting {wait} s ...")
            time.sleep(wait + random.uniform(0, 5))
        except urllib.error.URLError as e:
            print("   network problem:", e.reason)
            time.sleep(10)
    raise RuntimeError("no answer from Google Trends")


def pull(terms, time_range):
    req = {"comparisonItem": [{"keyword": t, "geo": "CH", "time": time_range} for t in terms],
           "category": 0, "property": ""}
    ex = get_json("/trends/api/explore", {"hl": "de", "tz": "-60", "req": json.dumps(req)})
    w = next(w for w in ex["widgets"] if w["id"] == "TIMESERIES")
    time.sleep(1.5)
    d = get_json("/trends/api/widgetdata/multiline",
                 {"hl": "de", "tz": "-60", "req": json.dumps(w["request"]), "token": w["token"]})
    return d["default"]["timelineData"]


def save(path, terms, timeline, label, fmt):
    """Write the same layout as the CSV export on the Trends website."""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        f.write("Category: All categories\n\n")
        wr = csv.writer(f)
        wr.writerow([label] + [f"{t}: (Switzerland)" for t in terms])
        for p in timeline:
            day = datetime.fromtimestamp(int(p["time"]), tz=timezone.utc).strftime(fmt)
            wr.writerow([day] + p["formattedValue"])


def terms_of(row):
    if (row.get("topic") or "").strip():
        return [row["topic"].strip()]  # Google topic, e.g. /m/084sq = wolf, all languages
    seen, out = set(), []
    for t in (row["de"], row["fr"], row["it"]):
        t = (t or "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def main():
    RAW.mkdir(exist_ok=True)
    today = date.today().isoformat()
    with open(HERE / "topics.csv", encoding="utf-8-sig") as f:
        topics = list(csv.DictReader(f, delimiter=";"))
    print("Warming up ...")
    opener.open(BASE + "/trends/explore?geo=CH", timeout=30).read()
    done, failed = 0, []
    for row in topics:
        terms = terms_of(row)
        for period, (time_range, label, fmt) in PERIODS.items():
            out = RAW / f"{row['key']}_{period}_{today}.csv"
            if out.exists():
                continue
            print(f"{row['de']} ({period}) ...")
            try:
                save(out, terms, pull(terms, time_range), label, fmt)
                done += 1
            except Exception as e:
                print("   failed:", e)
                failed.append(out.name)
            time.sleep(3 + random.uniform(0, 3))
    print(f"\n{done} files written to {RAW}")
    if failed:
        print("Not collected (run again later):", ", ".join(failed))
    input("Press Enter to close.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Stopped:", e)
        input("Press Enter to close.")
        sys.exit(1)
