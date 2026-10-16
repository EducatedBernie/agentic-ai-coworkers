"""Agent 1: DailyTechUpgradeAgent.

Finds the top 3 recent technical articles from trusted sources, personalized by
profile.json, past ratings, and weak topics from the career coach.

    python daily_tech.py
"""

import json
from datetime import date, timedelta

from agents import Agent, Runner, WebSearchTool
from agents.tool import WebSearchToolFilters
from pydantic import BaseModel, Field

from common import (BRIEFS_DIR, MODEL, OUTPUT, PROGRESS, RATINGS, SEEN_URLS,
                    load_json, load_profile, require_api_key, save_json)


class Article(BaseModel):
    title: str
    source: str = Field(description="Publisher, e.g. 'Anthropic Engineering Blog'")
    published_date: str = Field(description="YYYY-MM-DD, exactly as shown on the page")
    url: str = Field(description="Direct link to the article, copied from search results")
    summary: str = Field(description="3-4 sentence technical summary")
    key_takeaways: list[str] = Field(description="3 concrete technical takeaways")
    why_it_matters: str = Field(description="How this advances the reader's knowledge and career goals")
    reading_minutes: int


class DailyBrief(BaseModel):
    theme: str = Field(description="One line tying today's three articles together")
    articles: list[Article] = Field(description="Exactly 3 articles")
    suggested_order: str = Field(description="Which order to read them in and why")


def weak_topics(progress: list[dict]) -> list[str]:
    """Topics the career coach scored below 3/5 on average."""
    scores: dict[str, list[int]] = {}
    for p in progress:
        scores.setdefault(p["topic"], []).append(p["score"])
    return sorted(t for t, s in scores.items() if sum(s) / len(s) < 3)


def rating_feedback(ratings: dict) -> list[str]:
    """Titles you rated, so the agent can lean toward what you found useful."""
    lines = []
    for day in sorted(ratings)[-7:]:
        for item in ratings[day]:
            lines.append(f"{item['score']}/5 - {item['title']}")
    return lines


def build_prompt(profile: dict, today: date) -> str:
    cfg = profile["daily_brief"]
    since = today - timedelta(days=cfg["lookback_days"])
    seen = load_json(SEEN_URLS, [])[-100:]
    context = {
        "today": today.isoformat(),
        "published_on_or_after": since.isoformat(),
        "reading_budget_minutes": cfg["reading_minutes"],
        "interests": profile["interests"],
        "skills": profile["skills"],
        "career_goals": profile["career_goals"],
        "weak_topics_from_career_coach": weak_topics(load_json(PROGRESS, [])),
        "my_recent_ratings": rating_feedback(load_json(RATINGS, {})),
        "already_recommended_urls": seen,
    }
    return "Build today's brief for this learner:\n" + json.dumps(context, indent=2)


INSTRUCTIONS = """You are DailyTechUpgradeAgent, a technical learning curator.

Use web search to find exactly 3 high-quality technical articles or blog posts.
Rules:
- Only articles published on or after `published_on_or_after`. Verify the date on the page.
- Never recommend a URL in `already_recommended_urls`.
- Prefer deep technical content (engineering blogs, research write-ups, papers) over news or marketing.
- Cover different topics; at least one should address a `weak_topics_from_career_coach` item if any exist.
- Lean toward the kinds of articles rated 4-5 in `my_recent_ratings` and away from those rated 1-2.
- Total reading time should fit `reading_budget_minutes`.
- Copy URLs and dates exactly from the source. If you cannot confirm a date, pick another article.
- `why_it_matters` must reference the learner's specific goals or skill levels, not generic praise."""


def make_agent(profile: dict) -> Agent:
    domains = profile["daily_brief"]["trusted_domains"]
    return Agent(
        name="DailyTechUpgradeAgent",
        instructions=INSTRUCTIONS,
        tools=[WebSearchTool(filters=WebSearchToolFilters(allowed_domains=domains),
                             search_context_size="high")],
        output_type=DailyBrief,
        model=MODEL,
    )


def to_markdown(brief: DailyBrief, today: date) -> str:
    total = sum(a.reading_minutes for a in brief.articles)
    out = [f"# Daily Tech Brief: {today.isoformat()}", "",
           f"**Theme:** {brief.theme}  ", f"**Total reading time:** ~{total} min", "",
           f"**Suggested order:** {brief.suggested_order}", ""]
    for i, a in enumerate(brief.articles, 1):
        out += [f"## {i}. {a.title}",
                f"*{a.source}* | {a.published_date} | ~{a.reading_minutes} min  ",
                f"<{a.url}>", "", a.summary, "", "**Key takeaways**"]
        out += [f"- {t}" for t in a.key_takeaways]
        out += ["", f"**Why it matters for you:** {a.why_it_matters}", ""]
    out.append(f"_Rate this brief: `python evaluate.py rate {today.isoformat()} <s1> <s2> <s3>` (1-5 each)_")
    return "\n".join(out) + "\n"


def main() -> None:
    require_api_key()
    profile = load_profile()
    today = date.today()

    result = Runner.run_sync(make_agent(profile), build_prompt(profile, today))
    brief: DailyBrief = result.final_output

    if len(brief.articles) != 3:
        print(f"Warning: agent returned {len(brief.articles)} articles instead of 3.")

    save_json(BRIEFS_DIR / f"{today.isoformat()}.json", brief.model_dump())
    seen = load_json(SEEN_URLS, [])
    save_json(SEEN_URLS, seen + [a.url for a in brief.articles if a.url not in seen])

    md = to_markdown(brief, today)
    path = OUTPUT / "briefs" / f"{today.isoformat()}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(md)
    print(md)
    print(f"Saved to {path.relative_to(OUTPUT.parent)}")


if __name__ == "__main__":
    main()
