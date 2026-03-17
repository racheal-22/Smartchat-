"""
brain_gym_service.py — Daily Brain Gym Quiz Generator
======================================================
Generates 3-question quizzes for each Brain Gym category.

Categories:
  gk       → General Knowledge (AI generated, age-appropriate)
  sports   → Sports facts & current events (AI generated)
  puzzle   → Logic puzzles (AI generated)
  science  → Science fact of the day (AI generated)
  news     → Based on live NewsAPI headline (falls back to AI if no API key)

All quizzes return a list of dicts in the standard SmartChat format:
  [{question, options:{A,B,C,D}, correct_answer, why_correct, why_wrong, hint, dimension}]
"""

import json
import re
import urllib.request
import urllib.parse
from django.conf import settings

# Reuse existing safe Gemini call infrastructure
from .gemini_service import safe_generate_with_retry, SAFETY_PREFIX, _parse_quiz_json


# ── Category metadata shown in the UI ─────────────────────────────────────────

BRAIN_GYM_CATEGORIES = [
    {
        "key":         "gk",
        "emoji":       "🌍",
        "label":       "General Knowledge",
        "description": "Test your general awareness",
        "color":       "linear-gradient(135deg,#1d4ed8,#3b82f6)",
        "dimension":   "NARRATIVE",
    },
    {
        "key":         "sports",
        "emoji":       "⚽",
        "label":       "Sports Quiz",
        "description": "How well do you know sports?",
        "color":       "linear-gradient(135deg,#15803d,#22c55e)",
        "dimension":   "SYSTEMS",
    },
    {
        "key":         "puzzle",
        "emoji":       "🧩",
        "label":       "Puzzle Challenge",
        "description": "Sharpen your logical thinking",
        "color":       "linear-gradient(135deg,#7c3aed,#a855f7)",
        "dimension":   "LOGIC",
    },
    {
        "key":         "science",
        "emoji":       "🧪",
        "label":       "Science Fact",
        "description": "Explore the world of science",
        "color":       "linear-gradient(135deg,#b45309,#f59e0b)",
        "dimension":   "SYSTEMS",
    },
    {
        "key":         "news",
        "emoji":       "📰",
        "label":       "Today's News Quiz",
        "description": "Stay sharp with current affairs",
        "color":       "linear-gradient(135deg,#be123c,#f43f5e)",
        "dimension":   "NARRATIVE",
    },
]


# ── JSON quiz prompt template ──────────────────────────────────────────────────

def _quiz_prompt(topic_description: str, standard: int, dimension: str) -> str:
    return f"""
{SAFETY_PREFIX}

You are creating a fun, engaging quiz for a Class {standard} school student.

Topic: {topic_description}
Thinking dimension: {dimension}

Create exactly 5 multiple-choice questions. Each must be age-appropriate, educational,
and interesting. Questions should be clear and unambiguous.

Return ONLY a valid JSON array. No markdown. No code fences. No extra text.

[
  {{
    "question": "Question text here?",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
    "correct_answer": "A",
    "dimension": "{dimension}",
    "hint": "A short nudge without giving the answer away.",
    "solution": "Plain-English explanation of why the correct answer is right (1-2 sentences).",
    "why_correct": "Detailed reason why the correct answer is right.",
    "why_wrong": {{
      "B": "Why B is wrong",
      "C": "Why C is wrong",
      "D": "Why D is wrong"
    }}
  }}
]

Rules:
- Exactly 5 questions, 4 options each
- School-appropriate content only
- Return ONLY the JSON array
"""


# ── Live News fetcher ──────────────────────────────────────────────────────────

def _fetch_news_headline() -> str:
    """
    Fetch a top headline from NewsAPI.
    Returns a headline string, or a fallback topic if API key is missing / call fails.
    """
    api_key = getattr(settings, "NEWS_API_KEY", "")
    if not api_key:
        return "current world events and recent happenings around the globe"

    try:
        url = (
            "https://newsapi.org/v2/top-headlines"
            "?country=in&category=general&pageSize=5"
            f"&apiKey={api_key}"
        )
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        articles = data.get("articles", [])
        # Pick first headline that is long enough to be useful
        for article in articles:
            title = article.get("title", "")
            if title and len(title) > 20 and "[Removed]" not in title:
                return title
    except Exception as e:
        print(f"[BrainGym] NewsAPI fetch failed: {e}")

    return "current events and news happening around the world today"


# ── Per-category topic strings ─────────────────────────────────────────────────

def _topic_for(category_key: str, standard: int) -> str:
    topics = {
        "gk": (
            f"interesting general knowledge facts suitable for Class {standard} students "
            "— history, geography, science discoveries, famous personalities, world records"
        ),
        "sports": (
            "popular sports facts, famous athletes, sports rules and records, "
            "Olympic history, cricket, football, and other sports"
        ),
        "puzzle": (
            f"fun logic puzzles and brain teasers suitable for Class {standard} students "
            "— number patterns, riddles, sequence problems, lateral thinking"
        ),
        "science": (
            f"fascinating science facts for Class {standard} — about space, animals, "
            "human body, chemistry, physics, and the natural world"
        ),
    }
    return topics.get(category_key, f"general knowledge for Class {standard} students")


# ── Main public function ───────────────────────────────────────────────────────

def generate_brain_gym_quiz(category_key: str, standard: int) -> list:
    """
    Generate 3 quiz questions for the given Brain Gym category.

    Args:
        category_key: one of 'gk', 'sports', 'puzzle', 'science', 'news'
        standard:     student's class (int)

    Returns:
        List of question dicts in SmartChat quiz format.
        Empty list on failure (caller should handle gracefully).
    """
    # Find category metadata
    cat = next((c for c in BRAIN_GYM_CATEGORIES if c["key"] == category_key), None)
    if not cat:
        return []

    dimension = cat["dimension"]

    # Build topic description
    if category_key == "news":
        headline = _fetch_news_headline()
        topic_desc = (
            f"this news headline: \"{headline}\". "
            "Generate questions that help students understand the topic behind this headline. "
            "Make questions educational and appropriate for school students."
        )
    else:
        topic_desc = _topic_for(category_key, standard)

    prompt = _quiz_prompt(topic_desc, standard, dimension)
    raw = safe_generate_with_retry(prompt)

    if not raw:
        return []

    return _parse_quiz_json(raw, label=f"BrainGym:{category_key}")