"""Agent 2: nextLevelPersonalCoachForCareerLevel.

Interactive career coach: finds opportunities, drills you with interview
questions, scores your answers, and writes a Career Readiness Report.

    python coach.py

Commands inside the chat: /report, /progress, /reset, /quit
"""

import json
from datetime import date, datetime

from agents import Agent, Runner, SQLiteSession, WebSearchTool, function_tool

from common import (DATA, MODEL, OUTPUT, PROGRESS, load_json, load_profile,
                    require_api_key, save_json)


@function_tool
def record_assessment(topic: str, question: str, score: int, feedback: str) -> str:
    """Save the score for one answer the user gave.

    Args:
        topic: Short skill area, lowercase, reused consistently (e.g. "system design", "python", "rag").
        question: The question that was asked.
        score: 1 (no understanding) to 5 (interview-ready).
        feedback: One or two sentences on what was strong and what was missing.
    """
    if not 1 <= score <= 5:
        return "Error: score must be an integer from 1 to 5. Call again with a valid score."
    progress = load_json(PROGRESS, [])
    progress.append({
        "date": date.today().isoformat(),
        "topic": topic.strip().lower(),
        "question": question,
        "score": score,
        "feedback": feedback,
    })
    save_json(PROGRESS, progress)
    return f"Recorded {score}/5 for '{topic}'."


def summarize_progress() -> dict:
    progress = load_json(PROGRESS, [])
    topics: dict[str, list[dict]] = {}
    for p in progress:
        topics.setdefault(p["topic"], []).append(p)
    summary = {}
    for topic, items in sorted(topics.items()):
        scores = [i["score"] for i in items]
        summary[topic] = {
            "attempts": len(scores),
            "average": round(sum(scores) / len(scores), 2),
            "first": scores[0],
            "latest": scores[-1],
            "latest_feedback": items[-1]["feedback"],
        }
    return {"total_answers": len(progress), "by_topic": summary}


@function_tool
def get_progress() -> str:
    """Get the user's scores by topic from all past sessions (attempts, average, first and latest score)."""
    return json.dumps(summarize_progress(), indent=2)


def make_agent(profile: dict) -> Agent:
    instructions = f"""You are nextLevelPersonalCoachForCareerLevel, a demanding but supportive
technical career coach. Today is {date.today().isoformat()}.

Learner profile:
{json.dumps(profile, indent=2)}

What you do:
1. Opportunities: when asked, use web search to find current internships, jobs, research
   positions, or startup programs that match the profile. Give title, organization, link, and
   which required skills the learner has versus lacks. Only cite postings you actually found.
2. Interview drills: ask ONE question at a time (conceptual, coding, system design, or
   behavioral scenario), tuned to the target roles and to job descriptions you have found.
   Wait for the answer. Then evaluate it honestly: what was right, what was missing, a better
   answer, and a follow-up question that pushes deeper. Call record_assessment for every answer.
3. Gaps and plans: call get_progress before giving any assessment of strengths or weaknesses.
   Recommend specific resources (docs, courses, papers, projects) and a concrete weekly plan.

At the start of a conversation, call get_progress, then greet the learner with one sentence on
where they stand and offer: find opportunities, start a drill, or review progress.
Don't inflate scores. Keep replies concise; this is a chat, not an essay."""
    return Agent(
        name="nextLevelPersonalCoachForCareerLevel",
        instructions=instructions,
        tools=[WebSearchTool(), record_assessment, get_progress],
        model=MODEL,
    )


REPORT_PROMPT = """Write my Career Readiness Report now, in Markdown. Call get_progress first.
Sections:
1. Target roles and overall readiness score (0-100) with one-paragraph justification
2. Opportunities found (from this conversation, with links)
3. Technical assessment table: topic | attempts | average | trend (first -> latest)
4. Strengths
5. Knowledge gaps
6. Recommended resources (specific, with links)
7. 4-week preparation plan (week by week)
8. Next milestone and how we'll measure it
Output only the report."""


def main() -> None:
    require_api_key()
    agent = make_agent(load_profile())
    DATA.mkdir(exist_ok=True)
    session = SQLiteSession("coach", DATA / "coach.db")  # remembers past chats across runs

    started = datetime.now()
    transcript = OUTPUT / "sessions" / f"{started:%Y-%m-%d_%H%M}.md"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(f"# Coaching session: {started:%Y-%m-%d %H:%M}\n\n")

    def log(who: str, text: str) -> None:
        with transcript.open("a") as f:
            f.write(f"**{who}:** {text}\n\n")

    def ask(text: str) -> str | None:
        try:
            return Runner.run_sync(agent, text, session=session, max_turns=15).final_output
        except Exception as e:  # network/API errors shouldn't end the session
            print(f"\n[error] {type(e).__name__}: {e}\n")
            return None

    print("Career coach ready. Commands: /report  /progress  /reset  /quit\n")
    reply = ask("(session started)")
    if reply:
        print(f"Coach: {reply}\n")
        log("Coach", reply)

    while True:
        try:
            user = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        if user == "/quit":
            break
        if user == "/progress":
            print(json.dumps(summarize_progress(), indent=2), "\n")
            continue
        if user == "/reset":
            session.clear_session()
            print("Chat memory cleared (scores in data/progress.json are kept).\n")
            continue
        if user == "/report":
            report = ask(REPORT_PROMPT)
            if report:
                path = OUTPUT / "reports" / f"readiness-{date.today().isoformat()}.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(report + "\n")
                print(f"\n{report}\n\nSaved to {path.relative_to(OUTPUT.parent)}\n")
                log("Coach", f"(generated report: {path.name})")
            continue

        log("You", user)
        reply = ask(user)
        if reply:
            print(f"\nCoach: {reply}\n")
            log("Coach", reply)

    print(f"Transcript saved to {transcript.relative_to(OUTPUT.parent)}")


if __name__ == "__main__":
    main()
