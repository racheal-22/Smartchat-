"""
gemini_service.py — SmartChat AI Engine
========================================
Gemini-powered educational AI for NCERT-based school learning.
Produces rich, readable HTML notes — not flat boring text.
"""

import google.generativeai as genai
import json
import re
from django.conf import settings


# ──────────────────────────────────────────────────────────────────────
# Gemini Setup
# ──────────────────────────────────────────────────────────────────────

if not settings.GEMINI_API_KEY:
    raise Exception("GEMINI_API_KEY missing in settings")

genai.configure(api_key=settings.GEMINI_API_KEY)

model = genai.GenerativeModel(
    "gemini-3.1-flash-lite-preview",
    generation_config={
        "temperature": 0.3,
        "max_output_tokens": 2800,
    }
)


# ──────────────────────────────────────────────────────────────────────
# Dimension Classification
# ──────────────────────────────────────────────────────────────────────

_DIMENSION_RULES = {
    "LOGIC": [
        "calculate", "computation", "solve", "equation", "formula",
        "arithmetic", "algebra", "geometry", "trigonometry", "probability",
        "statistics", "proof", "theorem", "compute", "math", "maths",
        "number", "fraction", "decimal", "percentage", "ratio",
    ],
    "SYSTEMS": [
        "reason", "why", "how does", "explain", "cause", "effect",
        "analyse", "analyze", "compare", "difference", "relationship",
        "process", "mechanism", "system", "structure", "function",
        "law", "principle", "derive", "application", "logic behind",
        "evaluate", "deduce", "infer",
    ],
    "NARRATIVE": [
        "what is", "define", "describe", "meaning", "concept",
        "introduction", "overview", "history", "story", "origin",
        "understand", "explain to me", "tell me about", "summary",
        "notes", "chapter", "topic", "learn", "teach", "concept of",
    ],
    "SPATIAL": [
        "habit", "schedule", "routine", "daily", "revision", "plan",
        "consistency", "practice", "streak", "remember", "memorise",
        "memorize", "technique", "tip", "strategy", "study",
        "time management", "how to study", "improve",
    ],
}


def classify_dimension(text) -> str:
    """
    Classify a student interaction into one of the four XP dimensions.
    Returns the best-matching dimension (default: NARRATIVE).
    Accepts any type for `text` — coerces to str defensively.
    """
    lowered = str(text).lower() if text is not None else ""
    scores = {dim: 0 for dim in _DIMENSION_RULES}

    for dim, keywords in _DIMENSION_RULES.items():
        for kw in keywords:
            if kw in lowered:
                scores[dim] += 1

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "NARRATIVE"


# ──────────────────────────────────────────────────────────────────────
# Question-Type Classifier
# Determines which response STRUCTURE to use — separate from XP dimension.
# ──────────────────────────────────────────────────────────────────────

_QUESTION_TYPE_RULES = {
    "CALCULATION": [
        "calculate", "solve", "find the", "compute", "evaluate",
        "what is the value", "how much", "how many", "how long", "how far",
        "how tall", "how high", "how wide", "how deep", "how fast",
        "what is the length", "what is the area", "what is the volume",
        "what is the speed", "what is the force", "what is the mass",
        "what is the distance", "what is the time", "what is the height",
        "prove that", "show that", "using formula", "apply", "work out",
        "simplify", "expand", "factorise", "factorize", "differentiate",
        "integrate", "equation", "perimeter", "circumference", "diagonal",
        "hypotenuse", "resistance", "current", "voltage", "pressure",
        "velocity", "acceleration", "momentum", "kinetic energy",
    ],
    "STUDY_GUIDE": [
        "revise", "revision", "summarise", "summarize", "summary",
        "notes on", "key points", "important points", "cheat sheet",
        "quick recap", "exam tips", "how to remember", "memorise",
        "memorize", "memory tip", "flashcard", "overview of",
        "prepare for", "exam preparation", "study guide",
        "what are all", "list all", "give me all",
    ],
    "ANALYTICAL": [
        "compare", "contrast", "difference between", "similarities",
        "cause", "effect", "impact", "consequence", "reason for",
        "why did", "how did", "analyse", "analyze", "evaluate",
        "assess", "discuss", "to what extent", "advantages",
        "disadvantages", "pros and cons", "critically",
        "role of", "significance of", "importance of",
        "led to", "resulted in", "brought about",
    ],
}

def classify_question_type(text: str, subject: str = "") -> str:
    """
    Classify the student's question into one of four response structures:
      CALCULATION  → step-by-step solved examples with arithmetic
      CONCEPTUAL   → clear explanation, real-life analogy, no calculations
      ANALYTICAL   → cause-effect, comparison, reasoning
      STUDY_GUIDE  → revision notes, key points, memory tips

    Default: CONCEPTUAL
    """
    lowered = str(text or "").lower()
    subj    = str(subject or "").lower()

    scores = {k: 0 for k in _QUESTION_TYPE_RULES}
    for qtype, keywords in _QUESTION_TYPE_RULES.items():
        for kw in keywords:
            if kw in lowered:
                scores[qtype] += 1

    best       = max(scores, key=scores.get)
    best_score = scores[best]

    # If a clear winner, return it
    if best_score >= 1:
        return best

    # Default heuristic: maths/physics/chemistry → lean CALCULATION
    # for non-question messages (topic introductions etc.)
    calc_subjects = {"maths", "mathematics", "physics", "chemistry", "science"}
    if any(s in subj for s in calc_subjects):
        return "CALCULATION"

    return "CONCEPTUAL"


# ──────────────────────────────────────────────────────────────────────
# Grade Voice
# ──────────────────────────────────────────────────────────────────────

def grade_voice(standard):
    try:
        grade = int(standard)
    except Exception:
        grade = 8

    if grade <= 3:
        return (
            "You are a fun, warm teacher talking to a 7-9 year old. "
            "Use very short sentences. One idea at a time. "
            "Compare everything to toys, food, or games the child knows. "
            "Never use difficult words without explaining them immediately after."
        )
    elif grade <= 5:
        return (
            "You are a patient, encouraging teacher for a 10-11 year old. "
            "Use simple English. Explain with examples from home, school, or sports. "
            "Keep each paragraph to 2-3 sentences. Use 'imagine' and 'think of it like' often."
        )
    elif grade <= 7:
        return (
            "You are a clear, engaging teacher for a 12-13 year old. "
            "Introduce proper vocabulary but always explain new terms in brackets. "
            "Use relatable analogies. Connect ideas to things students see around them."
        )
    elif grade <= 9:
        return (
            "You are a knowledgeable teacher for a 14-15 year old (Class 9-10). "
            "Follow NCERT language precisely. Use correct scientific/mathematical terminology. "
            "Give logical reasoning. Formulas must be in plain text only. Never use LaTeX."
        )
    else:
        return (
            "You are an expert teacher for Class 11-12 students. "
            "Use NCERT board-level precision. Give derivations in plain text steps. "
            "Connect to real applications. Be analytical and exam-focused."
        )


# ──────────────────────────────────────────────────────────────────────
# Safety Prefix
# ──────────────────────────────────────────────────────────────────────

SAFETY_PREFIX = """
MANDATORY CHILD SAFETY RULES (never break these):
- This platform is used by school students aged 6-18. Parents trust this platform.
- NEVER produce adult content, violent content, hate speech, or politically biased content.
- NEVER discuss weapons, drugs, self-harm, gambling, or anything inappropriate for minors.
- NEVER discuss religion, politics, or controversial social topics.
- If the student's question is unrelated to their subject or topic, respond ONLY with:
  "That topic isn't part of your lesson. Let's stay focused on [TOPIC]!"
- Always use encouraging, positive, age-appropriate language.
- When in doubt, err on the side of caution and redirect to the lesson.
"""


# ──────────────────────────────────────────────────────────────────────
# Study Reference Links
# ──────────────────────────────────────────────────────────────────────

STUDY_LINKS = {
    "science":      [("NCERT", "https://ncert.nic.in/textbook.php"), ("BYJU'S Science", "https://byjus.com/science/"), ("Khan Academy", "https://www.khanacademy.org/science")],
    "physics":      [("NCERT", "https://ncert.nic.in/textbook.php"), ("BYJU'S Physics", "https://byjus.com/physics/"), ("Khan Academy Physics", "https://www.khanacademy.org/science/physics")],
    "chemistry":    [("NCERT", "https://ncert.nic.in/textbook.php"), ("BYJU'S Chemistry", "https://byjus.com/chemistry/"), ("Khan Academy Chemistry", "https://www.khanacademy.org/science/chemistry")],
    "biology":      [("NCERT", "https://ncert.nic.in/textbook.php"), ("BYJU'S Biology", "https://byjus.com/biology/"), ("Khan Academy Biology", "https://www.khanacademy.org/science/ap-biology")],
    "maths":        [("NCERT", "https://ncert.nic.in/textbook.php"), ("BYJU'S Maths", "https://byjus.com/maths/"), ("Khan Academy Maths", "https://www.khanacademy.org/math")],
    "mathematics":  [("NCERT", "https://ncert.nic.in/textbook.php"), ("BYJU'S Maths", "https://byjus.com/maths/"), ("Khan Academy Maths", "https://www.khanacademy.org/math")],
    "history":      [("NCERT", "https://ncert.nic.in/textbook.php"), ("BYJU'S History", "https://byjus.com/history/")],
    "geography":    [("NCERT", "https://ncert.nic.in/textbook.php"), ("BYJU'S Geography", "https://byjus.com/geography/")],
    "civics":       [("NCERT", "https://ncert.nic.in/textbook.php"), ("BYJU'S Civics", "https://byjus.com/civics/")],
    "social":       [("NCERT", "https://ncert.nic.in/textbook.php"), ("BYJU'S SST", "https://byjus.com/social-science/")],
    "economics":    [("NCERT", "https://ncert.nic.in/textbook.php"), ("BYJU'S Economics", "https://byjus.com/commerce/economics/")],
    "english":      [("NCERT", "https://ncert.nic.in/textbook.php"), ("British Council", "https://learnenglish.britishcouncil.org/")],
}

def render_study_links(subject) -> str:
    key   = str(subject or "").strip().lower()
    links = STUDY_LINKS.get(key, [
        ("NCERT Textbooks", "https://ncert.nic.in/textbook.php"),
        ("BYJU'S",          "https://byjus.com/"),
        ("Khan Academy",    "https://www.khanacademy.org/"),
    ])
    items = "".join(
        f'<a class="ref-link" href="{url}" target="_blank" rel="noopener noreferrer">'
        f'<span class="ref-icon">🔗</span>{name}</a>'
        for name, url in links
    )
    return (
        f'<div class="note-section note-refs-section">'
        f'<div class="note-section-label">📚 Study Further</div>'
        f'<div class="ref-links">{items}</div>'
        f'</div>'
    )


# ──────────────────────────────────────────────────────────────────────
# Build conversation history
# FIX: now handles both Django Message model objects AND plain dicts.
# Previously crashed: "'str' object has no attribute 'get'" because
# Message ORM objects don't support dict-style .get() calls.
# ──────────────────────────────────────────────────────────────────────

def _msg_attr(msg, key: str, default: str = "") -> str:
    """
    Safely read a field from either a plain dict or a Django model instance.
    """
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default) or default


def build_history(conversation) -> str:
    history = ""
    # Convert QuerySet to list before negative slicing — Django QuerySets
    # do not support negative indexing (raises ValueError).
    msgs = list(conversation) if hasattr(conversation, 'filter') else list(conversation)
    for msg in msgs[-4:]:
        role    = _msg_attr(msg, "role", "user")
        content = _msg_attr(msg, "content", "")

        # Strip HTML tags left over from bot responses, normalise whitespace
        content = re.sub(r"<[^>]+>", " ", content)
        content = re.sub(r"\s+", " ", content).strip()[:400]

        if content:
            history += f"{role.upper()}: {content}\n"

    return history or "This is the start of the session."


# ──────────────────────────────────────────────────────────────────────
# LaTeX and fence cleaner
# ──────────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    text = re.sub(r"```[\w]*\n?", "", text)
    text = re.sub(r"\n?```",      "", text)
    text = text.replace("$$", "").replace("$", "")
    text = text.replace("\\(", "").replace("\\)", "")
    text = text.replace("\\[", "").replace("\\]", "")
    text = re.sub(r"\\text\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\*?\{?", "", text)
    return text.strip()


# ──────────────────────────────────────────────────────────────────────
# Safe Gemini call
# ──────────────────────────────────────────────────────────────────────

def safe_generate(prompt: str) -> str | None:
    try:
        response = model.generate_content(prompt)
        if response and hasattr(response, "text"):
            return clean_text(response.text)
        return None
    except Exception as e:
        print("Gemini Error:", e)
        return None

def safe_generate_with_retry(prompt: str, retries: int = 2) -> str | None:
    for _ in range(retries):
        result = safe_generate(prompt)
        if result:
            return result
    return None


# ──────────────────────────────────────────────────────────────────────
# MAIN NOTE GENERATOR
# ──────────────────────────────────────────────────────────────────────

def generate_ai_response(conversation, standard, subject, topic, role="student"):
    """
    Generate a rich HTML study note in response to the conversation.

    `conversation` may be:
      - a QuerySet / list of Django Message model objects, OR
      - a list of plain dicts with keys 'role' and 'content'

    Returns:
        (html_string, dimension_string)
    """
    history = build_history(conversation)
    voice   = grade_voice(standard)
    links   = render_study_links(subject)

    # Classify dimension from the latest user message
    latest_user_content = ""
    for msg in reversed(list(conversation)):
        if _msg_attr(msg, "role", "user") == "user":
            latest_user_content = _msg_attr(msg, "content", "")
            break
    # Coerce to str — standard/topic may arrive as int from ORM fields
    dimension = classify_dimension(str(latest_user_content or topic or ""))

    if role == "teacher":
        prompt = f"""
{SAFETY_PREFIX}

You are an expert classroom teaching assistant helping a school teacher explain concepts
clearly to students. Provide teaching strategies, classroom examples, activities, analogies,
and ways to simplify the topic. Suggest how to introduce the concept to students, common
misconceptions to address, and ideas for engaging classroom activities or demonstrations.
You may also generate quiz questions or lesson plan outlines when asked.

TEACHER CONTEXT:
- Subject             : {subject}
- Topic               : {topic}
- Grade level taught  : {standard}

Recent Conversation:
{history}

CONTENT RULES:
- Focus on pedagogy: how to TEACH this topic, not just what it is.
- Suggest at least one classroom activity or demonstration.
- Highlight common student misconceptions about this topic.
- Write formulas in PLAIN TEXT only. NEVER use LaTeX.
- Structure your response clearly so the teacher can scan it quickly.
- Bold important terms and section headers using <strong>.
- Include 3-5 exam-style questions a teacher could use to assess students.

OUTPUT FORMAT:
Return ONLY clean HTML starting with <div class="note-block">
Do NOT include markdown. Do NOT include code fences. No explanations outside the HTML.
Replace every [placeholder in square brackets] with real content for "{topic}".

<div class="note-block">

  <div class="note-banner">
    <div class="note-banner-left">
      <span class="note-subject-tag">{subject}</span>
      <h2 class="note-title">Teaching: {topic}</h2>
      <p class="note-grade-tag">Grade {standard} &nbsp;&middot;&nbsp; Teacher Guide</p>
    </div>
    <div class="note-banner-icon">&#127979;</div>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#128161; Core Concept Overview</div>
    <p class="note-lead">[2-3 sentences summarising what {topic} is and why it matters in the curriculum.]</p>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#127979; How to Introduce This Topic</div>
    <p>[3-4 sentences: suggest an opening hook, question, or demonstration to capture student interest.]</p>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#128204; Key Concepts to Cover</div>
    <ul class="note-list">
      <li><strong>[Concept 1]</strong> — [How to explain it; suggested analogy or example.]</li>
      <li><strong>[Concept 2]</strong> — [How to explain it; common student confusion to watch for.]</li>
      <li><strong>[Concept 3]</strong> — [How to explain it; real-life connection.]</li>
      <li><strong>[Concept 4]</strong> — [How to explain it; exam importance.]</li>
    </ul>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#9888;&#65039; Common Student Misconceptions</div>
    <ul class="note-list">
      <li><strong>[Misconception 1]</strong> — [What students get wrong and how to correct it.]</li>
      <li><strong>[Misconception 2]</strong> — [Another common error and the correct understanding.]</li>
    </ul>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#127381; Classroom Activity / Demonstration</div>
    <div class="note-example-card">
      <div class="note-example-header">
        <span class="note-example-emoji">[Relevant emoji]</span>
        <strong>[Activity Name]</strong>
      </div>
      <p>[Describe a practical classroom activity or demonstration in 3-4 sentences. Include materials needed and what concept it illustrates.]</p>
    </div>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#9999;&#65039; Assessment Questions</div>
    <div class="note-qs">
      <div class="note-q note-q-easy">
        <div class="note-q-badge">1 Mark</div>
        <div class="note-q-text">[Simple recall question for formative assessment.]</div>
      </div>
      <div class="note-q note-q-easy">
        <div class="note-q-badge">1 Mark</div>
        <div class="note-q-text">[Another 1-mark question.]</div>
      </div>
      <div class="note-q note-q-medium">
        <div class="note-q-badge">2 Marks</div>
        <div class="note-q-text">[Short answer question testing understanding.]</div>
      </div>
      <div class="note-q note-q-medium">
        <div class="note-q-badge">2 Marks</div>
        <div class="note-q-text">[Application or explanation question.]</div>
      </div>
      <div class="note-q note-q-hots">
        <div class="note-q-badge">&#128293; HOTS</div>
        <div class="note-q-text">[Higher-order thinking question to challenge advanced students.]</div>
      </div>
    </div>
  </div>

</div>

FINAL CHECKS:
1. Replace EVERY [placeholder] with real content for "{topic}".
2. Return raw HTML ONLY. No markdown. Start directly with <div class="note-block">.
"""
    else:
        # ── Classify what the student is actually asking ──────────────────
        question_type = classify_question_type(latest_user_content, subject)

        # ── CALCULATION prompt ────────────────────────────────────────────
        if question_type == "CALCULATION":
            prompt = f"""
{SAFETY_PREFIX}

You are SmartChat, the best AI maths and science tutor for Indian school students.
You explain by showing, not just telling. Every concept gets a fully worked example.

STUDENT CONTEXT:
- Grade   : {standard}
- Subject : {subject}
- Topic   : {topic}

How to speak: {voice}
Recent Conversation:
{history}

CONTENT RULES:
- Follow NCERT syllabus strictly.
- Formulas in PLAIN TEXT only. No LaTeX, no $$, no backslashes.
- Show EVERY arithmetic step — never skip from question to answer.
- Use "you" and "your" throughout.
- Bold key terms with <strong>.

OUTPUT FORMAT — Return ONLY clean HTML starting with <div class="note-block">

<div class="note-block">
  <div class="note-banner">
    <div class="note-banner-left">
      <span class="note-subject-tag">{subject}</span>
      <h2 class="note-title">{topic}</h2>
      <p class="note-grade-tag">Class {standard} &nbsp;&middot;&nbsp; NCERT Aligned</p>
    </div>
    <div class="note-banner-icon">[One relevant emoji]</div>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#128161; Key Idea</div>
    <p class="note-lead">[2 sentences. State the core concept or formula needed to solve this type of problem. Be direct — the student wants to solve something.]</p>
    <div class="note-formula">
      <div class="note-formula-label">Formula / Rule</div>
      <div class="note-formula-text">[The formula in plain text. e.g. c squared = a squared + b squared]</div>
      <div class="note-formula-explain">[One sentence: what each variable means.]</div>
    </div>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#9999;&#65039; Solved Example 1 — Basic</div>
    <div class="note-example-card">
      <div class="note-example-header">
        <span class="note-example-emoji">&#128221;</span>
        <strong>[Short title describing what is being found]</strong>
      </div>
      <p><strong>Question:</strong> [A clear numerical problem using simple numbers. Give all values needed.]</p>
      <ol class="note-steps">
        <li><strong>Step 1 — Write Given &amp; Required:</strong> [List every value given. State what needs to be found. Write the formula you will use.]</li>
        <li><strong>Step 2 — Substitute:</strong> [Put the numbers into the formula. Show it written out fully.]</li>
        <li><strong>Step 3 — Calculate:</strong> [Show every arithmetic operation. No skipping. Write each intermediate result.]</li>
        <li><strong>&#10003; Answer:</strong> [Final value with correct units. One sentence of interpretation.]</li>
      </ol>
    </div>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#9999;&#65039; Solved Example 2 — Applied</div>
    <div class="note-example-card">
      <div class="note-example-header">
        <span class="note-example-emoji">&#128221;</span>
        <strong>[A real-world or slightly harder version of the same concept]</strong>
      </div>
      <p><strong>Question:</strong> [A real-life word problem using the same method. Different numbers and context from Example 1.]</p>
      <ol class="note-steps">
        <li><strong>Step 1 — Write Given &amp; Required:</strong> [Extract values from the word problem. State the unknown. Write formula.]</li>
        <li><strong>Step 2 — Substitute:</strong> [Full substitution shown. Rearrange formula if needed — show every algebraic step.]</li>
        <li><strong>Step 3 — Calculate:</strong> [Every arithmetic step written out explicitly.]</li>
        <li><strong>&#10003; Answer:</strong> [Final answer with units. Connect back to the real-world context.]</li>
      </ol>
    </div>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#9888;&#65039; Common Mistakes to Avoid</div>
    <ul class="note-list">
      <li><strong>[Mistake 1]</strong> — [What students get wrong and the correct approach.]</li>
      <li><strong>[Mistake 2]</strong> — [Another common error and how to avoid it.]</li>
    </ul>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#9889; Quick Revision</div>
    <div class="note-chips">
      <span class="note-chip">[Key term 1]</span>
      <span class="note-chip">[Key term 2]</span>
      <span class="note-chip">[Key term 3]</span>
      <span class="note-chip">[Key term 4]</span>
      <span class="note-chip">[Key term 5]</span>
    </div>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#9999;&#65039; Practice Questions</div>
    <div class="note-qs">
      <div class="note-q note-q-easy"><div class="note-q-badge">1 Mark</div><div class="note-q-text">[Direct formula application with given values.]</div></div>
      <div class="note-q note-q-easy"><div class="note-q-badge">1 Mark</div><div class="note-q-text">[Another straightforward calculation.]</div></div>
      <div class="note-q note-q-medium"><div class="note-q-badge">2 Marks</div><div class="note-q-text">[Multi-step problem needing rearrangement.]</div></div>
      <div class="note-q note-q-medium"><div class="note-q-badge">2 Marks</div><div class="note-q-text">[Real-world application problem.]</div></div>
      <div class="note-q note-q-hots"><div class="note-q-badge">&#128293; HOTS</div><div class="note-q-text">[Unfamiliar scenario requiring deep understanding of the concept.]</div></div>
    </div>
  </div>
</div>

FINAL CHECKS:
1. Replace EVERY [placeholder] with real content for "{topic}".
2. Show ALL arithmetic steps — every multiplication, addition, square root must be written out.
3. Return raw HTML ONLY. Start directly with <div class="note-block">.
"""

        # ── ANALYTICAL prompt ─────────────────────────────────────────────
        elif question_type == "ANALYTICAL":
            prompt = f"""
{SAFETY_PREFIX}

You are SmartChat, a brilliant study companion for Indian school students.
You help students think deeply — not just memorise, but truly understand causes, effects, and connections.

STUDENT CONTEXT:
- Grade   : {standard}
- Subject : {subject}
- Topic   : {topic}

How to speak: {voice}
Recent Conversation:
{history}

CONTENT RULES:
- Follow NCERT syllabus strictly. No off-syllabus content.
- Use "you" and "your" throughout.
- Bold key terms and concepts with <strong>.
- No numerical calculations unless directly relevant.
- For history/geography/civics: use real events, dates, people, places from NCERT.
- Write in flowing paragraphs for explanations, not just bullet points.

OUTPUT FORMAT — Return ONLY clean HTML starting with <div class="note-block">

<div class="note-block">
  <div class="note-banner">
    <div class="note-banner-left">
      <span class="note-subject-tag">{subject}</span>
      <h2 class="note-title">{topic}</h2>
      <p class="note-grade-tag">Class {standard} &nbsp;&middot;&nbsp; NCERT Aligned</p>
    </div>
    <div class="note-banner-icon">[One relevant emoji]</div>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#128161; The Core Question</div>
    <p class="note-lead">[2-3 sentences that frame the analytical question clearly. What are we comparing or analysing? Why does it matter? Make the student curious.]</p>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#128200; Cause &#8594; Effect Analysis</div>
    <p>[Write 4-5 sentences explaining the main causes OR factors. Each cause must be connected directly to its effect. Use "because", "which led to", "as a result" to show the chain of logic clearly.]</p>
    <ul class="note-list">
      <li><strong>[Cause / Factor 1]</strong> — [Its direct effect or significance. One meaningful sentence.]</li>
      <li><strong>[Cause / Factor 2]</strong> — [Its direct effect or significance.]</li>
      <li><strong>[Cause / Factor 3]</strong> — [Its direct effect or significance.]</li>
    </ul>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#127757; Real Example / Case Study</div>
    <div class="note-example-card">
      <div class="note-example-header">
        <span class="note-example-emoji">[Relevant emoji]</span>
        <strong>[Name of the real event, person, place, or case]</strong>
      </div>
      <p>[Describe a specific real-world example from NCERT in 3-4 sentences. Show how it illustrates the analytical concept. Connect it back with "This shows that..." or "This is a perfect example of..."]</p>
    </div>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#128204; Key Points to Remember</div>
    <ul class="note-list">
      <li><strong>[Key term or concept]</strong> — [One sentence explaining its analytical significance.]</li>
      <li><strong>[Key term or concept]</strong> — [Same format.]</li>
      <li><strong>[Key term or concept]</strong> — [Same format.]</li>
      <li><strong>[Key term or concept]</strong> — [Same format.]</li>
    </ul>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#129521; Step-by-Step Reasoning</div>
    <ol class="note-steps">
      <li>[Start with the background context — what was the situation before?]</li>
      <li>[Introduce the main factor, event, or turning point.]</li>
      <li>[Explain the immediate consequence or change.]</li>
      <li>[Explain the long-term significance or broader impact.]</li>
    </ol>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#9889; Quick Revision</div>
    <div class="note-chips">
      <span class="note-chip">[Key term 1]</span>
      <span class="note-chip">[Key term 2]</span>
      <span class="note-chip">[Key term 3]</span>
      <span class="note-chip">[Key term 4]</span>
      <span class="note-chip">[Key term 5]</span>
      <span class="note-chip">[Key term 6]</span>
    </div>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#9999;&#65039; Practice Questions</div>
    <div class="note-qs">
      <div class="note-q note-q-easy"><div class="note-q-badge">1 Mark</div><div class="note-q-text">[Recall question: state a cause, effect, or key fact.]</div></div>
      <div class="note-q note-q-easy"><div class="note-q-badge">1 Mark</div><div class="note-q-text">[Another recall question.]</div></div>
      <div class="note-q note-q-medium"><div class="note-q-badge">2 Marks</div><div class="note-q-text">[Explain a cause-effect relationship in 2-3 sentences.]</div></div>
      <div class="note-q note-q-medium"><div class="note-q-badge">2 Marks</div><div class="note-q-text">[Compare two events, people, or ideas.]</div></div>
      <div class="note-q note-q-hots"><div class="note-q-badge">&#128293; HOTS</div><div class="note-q-text">[Evaluate, assess, or argue: "To what extent..." or "Do you agree that..."]</div></div>
    </div>
  </div>
</div>

FINAL CHECKS:
1. Replace EVERY [placeholder] with real NCERT content for "{topic}".
2. Do NOT include any numerical calculations unless the question specifically requires them.
3. Return raw HTML ONLY. Start directly with <div class="note-block">.
"""

        # ── STUDY_GUIDE prompt ────────────────────────────────────────────
        elif question_type == "STUDY_GUIDE":
            prompt = f"""
{SAFETY_PREFIX}

You are SmartChat, the most helpful revision buddy for Indian school students.
Your job is to give students a clear, complete, and memorable revision guide they can use right before an exam.

STUDENT CONTEXT:
- Grade   : {standard}
- Subject : {subject}
- Topic   : {topic}

How to speak: {voice}
Recent Conversation:
{history}

CONTENT RULES:
- Follow NCERT syllabus strictly.
- Be concise but complete — every key point that could appear in an exam.
- Use "you" and "your" throughout.
- Bold important terms and formulas with <strong>.
- Memory tips must be genuinely helpful mnemonics or associations, not generic advice.

OUTPUT FORMAT — Return ONLY clean HTML starting with <div class="note-block">

<div class="note-block">
  <div class="note-banner">
    <div class="note-banner-left">
      <span class="note-subject-tag">{subject}</span>
      <h2 class="note-title">{topic} — Revision Guide</h2>
      <p class="note-grade-tag">Class {standard} &nbsp;&middot;&nbsp; Exam Ready</p>
    </div>
    <div class="note-banner-icon">&#128218;</div>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#9889; 60-Second Summary</div>
    <p class="note-lead">[3 sentences. What is this topic about in plain English? What is the ONE most important thing to remember? Make it stick.]</p>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#128204; Must-Know Key Points</div>
    <ul class="note-list">
      <li><strong>[Key point 1]</strong> — [One clear sentence. Exam-ready phrasing.]</li>
      <li><strong>[Key point 2]</strong> — [Same format.]</li>
      <li><strong>[Key point 3]</strong> — [Same format.]</li>
      <li><strong>[Key point 4]</strong> — [Same format.]</li>
      <li><strong>[Key point 5]</strong> — [Same format.]</li>
    </ul>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#128161; Memory Tips</div>
    <div class="note-example-card">
      <div class="note-example-header">
        <span class="note-example-emoji">&#129504;</span>
        <strong>How to Remember This</strong>
      </div>
      <p>[Give 2-3 genuine memory tricks: a mnemonic acronym, a rhyme, a vivid story, or a comparison to something students already know. Make it creative and memorable — not generic like "make flashcards".]</p>
    </div>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#129521; Step-by-Step Method (if applicable)</div>
    <ol class="note-steps">
      <li>[Step 1: The first thing to do or think about when approaching this topic in an exam.]</li>
      <li>[Step 2: The main concept or method to apply.]</li>
      <li>[Step 3: How to check your answer or conclude your response.]</li>
    </ol>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#9889; Quick Revision Chips</div>
    <div class="note-chips">
      <span class="note-chip">[Key term 1]</span>
      <span class="note-chip">[Key term 2]</span>
      <span class="note-chip">[Key term 3]</span>
      <span class="note-chip">[Key term 4]</span>
      <span class="note-chip">[Key term 5]</span>
      <span class="note-chip">[Key term 6]</span>
    </div>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#9999;&#65039; Most Likely Exam Questions</div>
    <div class="note-qs">
      <div class="note-q note-q-easy"><div class="note-q-badge">1 Mark</div><div class="note-q-text">[Define / State / Name question.]</div></div>
      <div class="note-q note-q-easy"><div class="note-q-badge">1 Mark</div><div class="note-q-text">[Another 1-mark question.]</div></div>
      <div class="note-q note-q-medium"><div class="note-q-badge">2 Marks</div><div class="note-q-text">[Explain / Describe question.]</div></div>
      <div class="note-q note-q-medium"><div class="note-q-badge">2 Marks</div><div class="note-q-text">[Compare / Give reasons question.]</div></div>
      <div class="note-q note-q-hots"><div class="note-q-badge">&#128293; HOTS</div><div class="note-q-text">[Application or evaluation question.]</div></div>
    </div>
  </div>
</div>

FINAL CHECKS:
1. Replace EVERY [placeholder] with real NCERT content for "{topic}".
2. Memory tips must be specific to this topic, not generic study advice.
3. Return raw HTML ONLY. Start directly with <div class="note-block">.
"""

        # ── CONCEPTUAL prompt (default) ───────────────────────────────────
        else:
            prompt = f"""
{SAFETY_PREFIX}

You are SmartChat, the best AI study companion for Indian school students.
Your notes feel like a conversation with a brilliant friend, not a boring textbook.

STUDENT CONTEXT:
- Grade   : {standard}
- Subject : {subject}
- Topic   : {topic}

How to speak: {voice}
Recent Conversation:
{history}

CONTENT RULES:
- Follow NCERT syllabus STRICTLY. No off-syllabus content.
- Write formulas in PLAIN TEXT only. NEVER use LaTeX, $$, or backslashes.
- Every concept needs a vivid real-life example the student can picture.
- Use "you" and "your" throughout. Speak directly to the student.
- Do NOT write dry textbook definitions. Explain like you are talking to a friend.
- Bold important words using <strong> tags.
- Write FULL paragraphs for explanations — not just bullet points.
- Do NOT include step-by-step numerical calculations — this is a theory explanation.
- Include 5 practice questions at the end.

OUTPUT FORMAT — Return ONLY clean HTML starting with <div class="note-block">

<div class="note-block">
  <div class="note-banner">
    <div class="note-banner-left">
      <span class="note-subject-tag">{subject}</span>
      <h2 class="note-title">{topic}</h2>
      <p class="note-grade-tag">Class {standard} &nbsp;&middot;&nbsp; NCERT Aligned</p>
    </div>
    <div class="note-banner-icon">[One relevant emoji for this topic]</div>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#128161; The Big Idea</div>
    <p class="note-lead">[2-3 sentences. Hook the student first with a surprising fact or question. Then explain what this topic actually is. Make it exciting. Use "you".]</p>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#128269; Understanding It Deeply</div>
    <p>[Write 4-6 full sentences explaining HOW and WHY this concept works. Introduce correct NCERT terminology but always explain each term in plain language right after.]</p>
    <div class="note-formula">
      <div class="note-formula-label">Key Formula / Rule</div>
      <div class="note-formula-text">[Formula in plain text. REMOVE THIS BLOCK ENTIRELY if no formula exists for this topic.]</div>
      <div class="note-formula-explain">[One sentence: what each part means.]</div>
    </div>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#128204; Key Points</div>
    <ul class="note-list">
      <li><strong>[Important term]</strong> — [One meaningful sentence. Not a definition — explain why it matters.]</li>
      <li><strong>[Important term]</strong> — [Same format.]</li>
      <li><strong>[Important term]</strong> — [Same format.]</li>
      <li><strong>[Important term]</strong> — [Same format.]</li>
    </ul>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#127757; Real Life Example</div>
    <div class="note-example-card">
      <div class="note-example-header">
        <span class="note-example-emoji">[Relevant emoji]</span>
        <strong>[Catchy short title for this example]</strong>
      </div>
      <p>[Describe a vivid, concrete real-world example in 3-4 sentences. Connect it back to the concept at the end.]</p>
    </div>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#129521; Think It Through — Step by Step</div>
    <ol class="note-steps">
      <li>[Start from what the student already knows. Build the bridge to the new idea.]</li>
      <li>[Introduce the core mechanism. Explain what happens and why.]</li>
      <li>[Complete the picture. Show how all the pieces connect.]</li>
    </ol>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#9889; Quick Revision</div>
    <div class="note-chips">
      <span class="note-chip">[Key term 1]</span>
      <span class="note-chip">[Key term 2]</span>
      <span class="note-chip">[Key term 3]</span>
      <span class="note-chip">[Key term 4]</span>
      <span class="note-chip">[Key term 5]</span>
      <span class="note-chip">[Key term 6]</span>
    </div>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#9999;&#65039; Practice Questions</div>
    <div class="note-qs">
      <div class="note-q note-q-easy"><div class="note-q-badge">1 Mark</div><div class="note-q-text">[NCERT-style 1-mark question.]</div></div>
      <div class="note-q note-q-easy"><div class="note-q-badge">1 Mark</div><div class="note-q-text">[Another 1-mark question.]</div></div>
      <div class="note-q note-q-medium"><div class="note-q-badge">2 Marks</div><div class="note-q-text">[2-mark question.]</div></div>
      <div class="note-q note-q-medium"><div class="note-q-badge">2 Marks</div><div class="note-q-text">[Another 2-mark question.]</div></div>
      <div class="note-q note-q-hots"><div class="note-q-badge">&#128293; HOTS</div><div class="note-q-text">[Higher Order Thinking question.]</div></div>
    </div>
  </div>
</div>

FINAL CHECKS BEFORE RETURNING:
1. Replace EVERY [placeholder in square brackets] with real content for "{topic}".
2. If there is no formula for this topic, completely remove the note-formula div block.
3. Do NOT add solved numerical examples — this is a CONCEPTUAL response.
4. Return raw HTML ONLY. No explanations. No markdown fences. Start directly with <div class="note-block">.
"""

    html = safe_generate_with_retry(prompt)

    if not html:
        return _fallback_response(topic, subject), dimension

    if not html.strip().startswith("<"):
        html = _markdown_to_note_html(html, topic, subject, standard)

    # Inject study reference links before the final closing </div>
    html = html.rstrip()
    if html.endswith("</div>"):
        html = html[:-6] + links + "</div>"

    return html, dimension


# ──────────────────────────────────────────────────────────────────────
# SESSION INTRO
# ──────────────────────────────────────────────────────────────────────

def generate_session_intro(topic, standard):
    """
    Generate a welcoming HTML intro card for a new chat session.
    Returns (html_string, dimension_string).
    """
    voice = grade_voice(standard)
    dimension = classify_dimension(str(topic or ""))

    prompt = f"""
{SAFETY_PREFIX}

You are SmartChat, a friendly AI teacher, welcoming a Grade {standard} student to a new lesson.

Topic : {topic}
Voice : {voice}

Return ONLY clean HTML. Replace all placeholder text. No markdown. No code fences.

<div class="note-block">

  <div class="note-banner intro-banner">
    <div class="note-banner-left">
      <span class="note-subject-tag">New Session</span>
      <h2 class="note-title">Let's explore: {topic}</h2>
      <p class="note-grade-tag">Class {standard} &nbsp;&middot;&nbsp; NCERT Aligned</p>
    </div>
    <div class="note-banner-icon">&#128075;</div>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#128214; What is this about?</div>
    <p class="note-lead">[2-3 sentences. Explain {topic} simply. Start with "Imagine..." or "Have you ever noticed...". Make the student curious and excited.]</p>
  </div>

  <div class="note-section note-section-alt">
    <div class="note-section-label">&#127919; Why does this matter?</div>
    <p>[2 sentences. Tell the student why {topic} is important — in real life or in their future studies.]</p>
  </div>

  <div class="note-section">
    <div class="note-section-label">&#128506;&#65039; What we will learn</div>
    <ul class="note-list">
      <li><strong>[Concept 1 name]</strong> — [One sentence preview]</li>
      <li><strong>[Concept 2 name]</strong> — [One sentence preview]</li>
      <li><strong>[Concept 3 name]</strong> — [One sentence preview]</li>
    </ul>
  </div>

  <div class="note-section note-cta-section">
    <p class="note-cta">Ready to dive in? Ask me your first question about <strong>{topic}</strong> &#128640;</p>
  </div>

</div>

Replace all placeholders with real content. Return raw HTML only.
"""

    html = safe_generate_with_retry(prompt)

    if not html:
        return (
            f'<div class="note-block"><div class="note-section">'
            f'<p class="note-lead">Welcome! Let\'s start learning about <strong>{topic}</strong>. Ask me anything!</p>'
            f'</div></div>'
        ), dimension

    if not html.strip().startswith("<"):
        html = f'<div class="note-block"><div class="note-section"><p class="note-lead">{html}</p></div></div>'

    return html, dimension


# ──────────────────────────────────────────────────────────────────────
# CHAT QUIZ GENERATOR
# ──────────────────────────────────────────────────────────────────────

def generate_chat_quiz(standard, topic, explanation):
    """
    Generate 4 MCQs based on the last AI explanation in a chat session.
    Each question includes a 'dimension' field for XP routing.
    """
    clean_exp = re.sub(r"<[^>]+>", " ", explanation)
    clean_exp = re.sub(r"\s+", " ", clean_exp).strip()[:1500]

    prompt = f"""
{SAFETY_PREFIX}

Create exactly 5 multiple-choice quiz questions for a Class {standard} student.
Topic: {topic}
Based on this lesson content: {clean_exp}

Return a valid JSON array ONLY. No markdown. No code fences.

RULES:
1. Exactly 5 questions:
   - Question 1: easy recall → dimension: "NARRATIVE"
   - Question 2: understanding / explanation → dimension: "SYSTEMS"
   - Question 3: calculation or formula application → dimension: "LOGIC"
   - Question 4: real-life scenario / application → dimension: "SYSTEMS"
   - Question 5: higher-order thinking / analysis → dimension: "LOGIC"
2. Every question MUST include all fields shown below — especially why_correct and why_wrong.
3. "solution": a plain-English explanation of the correct answer (1-2 sentences).
4. "why_correct": detailed reason why the correct option is right.
5. "why_wrong": object with a key for EACH wrong option explaining why it is incorrect.
6. "hint": one short sentence nudging toward the answer without giving it away.
7. Tone: Encouraging and educational.
8. Output: Valid JSON only. No markdown. No code fences.

[
  {{
    "question": "...",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
    "correct_answer": "A",
    "dimension": "NARRATIVE",
    "hint": "Think about what this concept means at its core.",
    "solution": "The correct answer is A because...",
    "why_correct": "A is correct because... (detailed explanation)",
    "why_wrong": {{
      "B": "B is wrong because...",
      "C": "C is wrong because...",
      "D": "D is wrong because..."
    }}
  }}
]
"""

    text = safe_generate_with_retry(prompt)
    if not text:
        return []
    return _parse_quiz_json(text, label="Chat Quiz")


# ──────────────────────────────────────────────────────────────────────
# DAILY THINKING QUIZ
# ──────────────────────────────────────────────────────────────────────

def generate_daily_quiz(standard, dimension):
    """
    Generate 5 MCQs targeted at a specific thinking dimension.
    """
    dimension_instructions = {
        "LOGIC": (
            "Focus on calculation, number problems, and formula application. "
            "Each question should require the student to compute or solve something step by step."
        ),
        "SYSTEMS": (
            "Focus on reasoning, cause-and-effect, and analytical thinking. "
            "Questions should ask WHY or HOW something works, not just WHAT it is."
        ),
        "NARRATIVE": (
            "Focus on concept recall, definitions, and conceptual understanding. "
            "Questions should test whether the student understands the core ideas of a topic."
        ),
        "SPATIAL": (
            "Focus on study strategies, memory techniques, learning consistency, and patterns. "
            "Questions should help students reflect on HOW to learn effectively."
        ),
    }

    dim_guide = dimension_instructions.get(
        dimension.upper(),
        dimension_instructions["NARRATIVE"]
    )

    prompt = f"""
{SAFETY_PREFIX}

Create exactly 5 multiple-choice questions for a Class {standard} student.

Thinking Dimension: {dimension}
Dimension Focus: {dim_guide}

Design questions that genuinely train this thinking skill.
Questions should be school-appropriate and curriculum-connected.
All 5 questions must have "dimension": "{dimension}" in their JSON.

Return a valid JSON array ONLY. No markdown. No code fences.

[
  {{
    "question": "Question text here?",
    "options": {{
      "A": "Option A",
      "B": "Option B",
      "C": "Option C",
      "D": "Option D"
    }},
    "correct_answer": "A",
    "dimension": "{dimension}",
    "hint": "A short nudge to help the student think in the right direction without revealing the answer.",
    "solution": "Clear explanation of the correct answer.",
    "why_correct": "Detailed reason why the correct answer is right.",
    "why_wrong": {{
      "B": "Why B is wrong",
      "C": "Why C is wrong",
      "D": "Why D is wrong"
    }}
  }}
]

Rules:
- Exactly 5 questions
- 4 options each (A B C D)
- Each question must include a "hint" field
- Class {standard} appropriate
- Return ONLY the JSON array
"""

    text = safe_generate_with_retry(prompt)
    if not text:
        return []
    return _parse_quiz_json(text, label="Daily Quiz")


# ──────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────

def _parse_quiz_json(text: str, label: str = "Quiz") -> list:
    text = re.sub(r"^```[\w]*\n?", "", text.strip())
    text = re.sub(r"\n?```$", "", text).strip()
    start = text.find("[")
    if start == -1:
        print(f"{label}: no JSON array found\n{text[:300]}")
        return []
    text = text[start:]
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)

    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        pass

    top_keys = r'(?:correct_answer|solution|hint|answer|explanation|correct|key|dimension)'
    text = re.sub(r'("(?:[^"\\]|\\.)*")\s*\n(\s*),\s*\n(\s*"' + top_keys + r'")', r'\1\n\2}\n\2,\n\3', text)
    text = re.sub(r'("(?:[^"\\]|\\.)*")\s*\n(\s*),\s*\n(\s*\{)', r'\1\n\2}\n\2,\n\3', text)
    text = re.sub(r',\s*([}\]])', r'\1', text)

    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        pass

    text = _close_truncated_json(text)
    text = re.sub(r',\s*([}\]])', r'\1', text)

    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        print(f"{label} JSON unrecoverable:\n{text[:400]}")
        return []


def _close_truncated_json(text: str) -> str:
    stack, in_string, escape_next = [], False, False
    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ("{", "["):
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()
    closing = ('"' if in_string else "") + "".join("}" if o == "{" else "]" for o in reversed(stack))
    return text + closing


def _fallback_response(topic: str, subject: str = "") -> str:
    return (
        f'<div class="note-block"><div class="note-section">'
        f'<p class="note-lead">I couldn\'t generate notes for <strong>{topic}</strong> right now. '
        f'Please try asking again!</p>'
        f'</div></div>'
    )


def _markdown_to_note_html(text: str, topic: str, subject: str, standard) -> str:
    text = re.sub(r"^### (.+)$", r"<h3>\1</h3>", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.+)$",  r"<h2>\1</h2>", text, flags=re.MULTILINE)
    text = re.sub(r"^# (.+)$",   r"<h1>\1</h1>", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*",     r"<em>\1</em>", text)
    text = re.sub(r"^[*\-•] (.+)$", r"<li>\1</li>", text, flags=re.MULTILINE)
    text = re.sub(r"(<li>.*?</li>)+", lambda m: f"<ul class='note-list'>{m.group()}</ul>", text, flags=re.DOTALL)
    text = text.replace("\n\n", "<br><br>")
    return (
        f'<div class="note-block">'
        f'<div class="note-banner"><div class="note-banner-left">'
        f'<span class="note-subject-tag">{subject}</span>'
        f'<h2 class="note-title">{topic}</h2>'
        f'<p class="note-grade-tag">Class {standard}</p>'
        f'</div></div>'
        f'<div class="note-section">{text}</div>'
        f'</div>'
    )