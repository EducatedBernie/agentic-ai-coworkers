"""Evaluation for both agents.

    python evaluate.py                        # write output/evaluation.md
    python evaluate.py rate 2026-10-16 5 4 3  # rate that day's 3 articles (1-5)

Agent 1 accuracy is checked automatically (does the URL load, is the date in the
lookback window, is it from a trusted domain, is it a repeat). Usefulness comes
from your ratings. Agent 2 progress comes from scores in data/progress.json.
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from urllib.parse import urlparse

import requests

from common import BRIEFS_DIR, OUTPUT, PROGRESS, RATINGS, load_json, load_profile, save_json

HEADERS = {"User-Agent": "Mozilla/5.0 (DailyTechUpgradeAgent link checker)"}


def check_url(url: str) -> str:
    """'ok', 'blocked' (site refuses bots, so unverified), or 'broken'."""
    try:
        r = requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True)
        if r.status_code in (403, 405) or r.status_code >= 500:
            r = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True, stream=True)
            r.close()
        if r.status_code < 400:
            return "ok"
        if r.status_code in (401, 403, 429):
            return "blocked"
        return "broken"
    except requests.RequestException:
        return "broken"


def is_trusted(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def date_in_window(published: str, brief_day: date, lookback: int) -> bool:
    try:
        d = date.fromisoformat(published)
    except ValueError:
        return False
    return brief_day - timedelta(days=lookback) <= d <= brief_day


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}% ({n}/{d})" if d else "n/a"


def evaluate_briefs(profile: dict) -> list[str]:
    cfg = profile["daily_brief"]
    files = sorted(BRIEFS_DIR.glob("*.json")) if BRIEFS_DIR.exists() else []
    if not files:
        return ["No briefs yet. Run `python daily_tech.py` first."]

    rows, seen = [], set()
    for f in files:
        day = date.fromisoformat(f.stem)
        for a in load_json(f, {}).get("articles", []):
            rows.append({"day": day, **a,
                         "date_ok": date_in_window(a["published_date"], day, cfg["lookback_days"]),
                         "trusted": is_trusted(a["url"], cfg["trusted_domains"]),
                         "repeat": a["url"] in seen})
            seen.add(a["url"])

    with ThreadPoolExecutor(max_workers=8) as pool:
        for row, status in zip(rows, pool.map(check_url, [r["url"] for r in rows])):
            row["link"] = status

    n = len(rows)
    ok = sum(r["link"] == "ok" for r in rows)
    blocked = sum(r["link"] == "blocked" for r in rows)
    out = ["## Agent 1: DailyTechUpgradeAgent", "",
           f"Briefs: {len(files)}, articles: {n}", "",
           "| Metric | Result |", "|---|---|",
           f"| Link loads | {pct(ok, n)} (+{blocked} blocked by site, unverified) |",
           f"| Date within {cfg['lookback_days']}-day window | {pct(sum(r['date_ok'] for r in rows), n)} |",
           f"| From trusted domain | {pct(sum(r['trusted'] for r in rows), n)} |",
           f"| No repeats across days | {pct(sum(not r['repeat'] for r in rows), n)} |",
           f"| Exactly 3 articles per brief | {pct(sum(len(load_json(f, {}).get('articles', [])) == 3 for f in files), len(files))} |"]

    ratings = load_json(RATINGS, {})
    scores = [i["score"] for day in ratings.values() for i in day]
    if scores:
        out.append(f"| Your usefulness rating | {sum(scores) / len(scores):.1f}/5 over {len(scores)} articles |")

    problems = [r for r in rows if r["link"] == "broken" or not r["date_ok"] or not r["trusted"] or r["repeat"]]
    if problems:
        out += ["", "**Flagged articles**", ""]
        for r in problems:
            issues = [k for k, bad in [("broken link", r["link"] == "broken"), ("date out of window", not r["date_ok"]),
                                       ("untrusted domain", not r["trusted"]), ("repeat", r["repeat"])] if bad]
            out.append(f"- {r['day']}: [{r['title']}]({r['url']}) ({r['published_date']}): {', '.join(issues)}")
    return out


def evaluate_coach() -> list[str]:
    progress = load_json(PROGRESS, [])
    if not progress:
        return ["## Agent 2: Career Coach", "", "No scored answers yet. Run `python coach.py` and do a drill."]

    topics: dict[str, list[int]] = {}
    for p in progress:
        topics.setdefault(p["topic"], []).append(p["score"])
    out = ["## Agent 2: Career Coach", "",
           f"Scored answers: {len(progress)} across {len(topics)} topics, "
           f"{len({p['date'] for p in progress})} day(s)", "",
           "| Topic | Attempts | Average | First -> Latest |", "|---|---|---|---|"]
    for t, s in sorted(topics.items(), key=lambda kv: sum(kv[1]) / len(kv[1])):
        out.append(f"| {t} | {len(s)} | {sum(s) / len(s):.1f} | {s[0]} -> {s[-1]} |")

    half = len(progress) // 2
    if half:
        early = sum(p["score"] for p in progress[:half]) / half
        late = sum(p["score"] for p in progress[half:]) / (len(progress) - half)
        out += ["", f"Average score, first half of answers vs second half: **{early:.2f} -> {late:.2f}**"]
    weak = [t for t, s in topics.items() if sum(s) / len(s) < 3]
    if weak:
        out.append(f"Weak topics (avg < 3, fed back into Agent 1's article picks): {', '.join(sorted(weak))}")
    return out


def rate(day: str, scores: list[str]) -> None:
    path = BRIEFS_DIR / f"{day}.json"
    if not path.exists():
        raise SystemExit(f"No brief for {day}.")
    articles = load_json(path, {})["articles"]
    try:
        values = [int(s) for s in scores]
    except ValueError:
        raise SystemExit("Scores must be integers 1-5.")
    if len(values) != len(articles) or not all(1 <= v <= 5 for v in values):
        raise SystemExit(f"Give {len(articles)} scores, each 1-5.")
    ratings = load_json(RATINGS, {})
    ratings[day] = [{"title": a["title"], "url": a["url"], "score": v} for a, v in zip(articles, values)]
    save_json(RATINGS, ratings)
    print(f"Saved ratings for {day}. Future briefs will use them for personalization.")


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "rate":
        if len(sys.argv) < 4:
            raise SystemExit("Usage: python evaluate.py rate YYYY-MM-DD s1 s2 s3")
        return rate(sys.argv[2], sys.argv[3:])

    report = "\n".join([f"# Agent Evaluation: {date.today().isoformat()}", "",
                        *evaluate_briefs(load_profile()), "", *evaluate_coach()]) + "\n"
    path = OUTPUT / "evaluation.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report)
    print(report)
    print(f"Saved to {path.relative_to(OUTPUT.parent)}")


if __name__ == "__main__":
    main()
