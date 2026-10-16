"""Shared paths and JSON helpers for both agents and the evaluator."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
PROFILE = ROOT / "profile.json"

SEEN_URLS = DATA / "seen_urls.json"      # Agent 1: URLs already recommended
RATINGS = DATA / "ratings.json"          # Agent 1: your 1-5 usefulness ratings per brief
PROGRESS = DATA / "progress.json"        # Agent 2: scored interview answers
BRIEFS_DIR = DATA / "briefs"             # Agent 1: raw structured briefs (used by the evaluator)

load_dotenv(ROOT / ".env")

# None -> the Agents SDK default model. Set OPENAI_MODEL in .env to override.
MODEL = os.getenv("OPENAI_MODEL") or None


def require_api_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key.")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"{path} is not valid JSON ({e}). Fix or delete it.")


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)  # atomic, so a crash never leaves a half-written file


def load_profile() -> dict:
    profile = load_json(PROFILE, None)
    if profile is None:
        raise SystemExit(f"Missing {PROFILE}.")
    return profile
