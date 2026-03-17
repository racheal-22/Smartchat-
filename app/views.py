from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Avg, Sum, Q
from django.utils import timezone

from .models import (
    CustomUser,
    StudentProfile,
    ChatSession,
    Message,
    SessionNote,
    QuizSession,
    QuizQuestion,
    TopicMastery,
)
from .brain_gym_service import generate_brain_gym_quiz, BRAIN_GYM_CATEGORIES
from .gemini_service import (
    generate_ai_response,
    generate_session_intro,
    generate_daily_quiz,
    generate_chat_quiz,
)

import markdown
import json


# ─────────────────────────────────────────────────────────────
# Auth Views
# ─────────────────────────────────────────────────────────────

@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "Logged out successfully.")
    return redirect("login")


def landing_page(request):
    return render(request, "landing.html")


def login_view(request):
    if request.user.is_authenticated:
        if request.user.role == "teacher":
            return redirect("teacher_school_dashboard")
        return redirect("student_dashboard")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        if not username or not password:
            messages.error(request, "All fields are required.")
            return render(request, "login.html")

        user = authenticate(request, username=username, password=password)

        if user is None:
            messages.error(request, "Invalid username or password.")
            return render(request, "login.html")

        if not user.is_active:
            messages.error(request, "Account is disabled. Contact admin.")
            return render(request, "login.html")

        login(request, user)

        next_url = request.GET.get("next")
        if next_url:
            return redirect(next_url)

        if user.role == "teacher":
            return redirect("teacher_school_dashboard")
        return redirect("student_dashboard")

    return render(request, "login.html")


def signup_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        role = request.POST.get("role")
        standard = request.POST.get("standard")
        school_name = request.POST.get("school_name")

        if CustomUser.objects.filter(username=username).exists():
            return redirect("signup")

        user = CustomUser.objects.create_user(
            username=username,
            password=password,
            role=role,
            standard=standard if role == "student" else None,
            school_name=school_name if role == "teacher" else None,
        )

        login(request, user)

        if role == "teacher":
            return redirect("teacher_school_dashboard")
        return redirect("student_dashboard")

    return render(request, "signup.html")


def student_signup(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()
        standard = request.POST.get("standard")
        division = request.POST.get("division", "").strip()
        roll_number = request.POST.get("roll_number")
        school_name = request.POST.get("school_name", "").strip()

        if not username or not password:
            messages.error(request, "Username and Password are required.")
            return render(request, "student_signup.html")

        if not school_name:
            messages.error(request, "School name is required.")
            return render(request, "student_signup.html")

        if not standard:
            messages.error(request, "Standard is required.")
            return render(request, "student_signup.html")

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return render(request, "student_signup.html")

        user = CustomUser.objects.create_user(
            username=username,
            password=password,
            role="student",
            standard=int(standard),
            division=division,
            roll_number=roll_number,
            school_name=school_name,
        )

        StudentProfile.objects.create(user=user)

        messages.success(request, "Account created successfully. Please login.")
        return redirect("login")

    return render(request, "student_signup.html")


def teacher_signup(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return render(request, "teacher_signup.html")

        CustomUser.objects.create_user(
            username=username,
            password=password,
            role="teacher",
            school_name=request.POST.get("school_name"),
        )

        messages.success(request, "Teacher account created successfully. Please login.")
        return redirect("login")

    return render(request, "teacher_signup.html")


# ─────────────────────────────────────────────────────────────
# Student Dashboard
# ─────────────────────────────────────────────────────────────

@login_required
def student_dashboard(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)

    dimension_map = {
        "Logic": profile.xp_logic,
        "Systems": profile.xp_systems,
        "Narrative": profile.xp_narrative,
        "Spatial": profile.xp_spatial,
    }

    dominant_dimension = max(dimension_map, key=dimension_map.get)
    weakest_dimension = min(dimension_map, key=dimension_map.get)

    total = sum(dimension_map.values()) or 1
    dominant_percent = round((dimension_map[dominant_dimension] / total) * 100)
    weakest_percent = round((dimension_map[weakest_dimension] / total) * 100)

    subject_counts = (
        ChatSession.objects
        .filter(user=request.user)
        .values("subject")
        .annotate(count=Count("id"))
    )

    strongest_subject = None
    weakest_subject = None
    if subject_counts:
        strongest_subject = max(subject_counts, key=lambda x: x["count"])["subject"]
        weakest_subject = min(subject_counts, key=lambda x: x["count"])["subject"]

    leaderboard_profiles = (
        StudentProfile.objects
        .filter(user__standard=request.user.standard)
        .select_related("user")
    )
    leaderboard = sorted(
        leaderboard_profiles,
        key=lambda p: p.leaderboard_score,
        reverse=True
    )[:5]

    return render(request, "dashboard.html", {
        "profile": profile,
        "dominant_dimension": dominant_dimension,
        "weakest_dimension": weakest_dimension,
        "strongest_subject": strongest_subject,
        "weakest_subject": weakest_subject,
        "leaderboard": leaderboard,
        "dominant_percent": dominant_percent,
        "weakest_percent": weakest_percent,
        "brain_gym_categories": BRAIN_GYM_CATEGORIES,
    })


# ─────────────────────────────────────────────────────────────
# Student Analytics
# ─────────────────────────────────────────────────────────────

@login_required
def analytics_view(request):
    profile = StudentProfile.objects.get(user=request.user)

    xp_values = [
        profile.xp_logic,
        profile.xp_systems,
        profile.xp_narrative,
        profile.xp_spatial,
    ]
    max_xp = max(xp_values)
    min_xp = min(xp_values)

    balance_score = 0 if max_xp == 0 else round(
        100 - ((max_xp - min_xp) / (max_xp + 1) * 100), 2
    )

    dimension_map = {
        "Logic": profile.xp_logic,
        "Systems": profile.xp_systems,
        "Narrative": profile.xp_narrative,
        "Spatial": profile.xp_spatial,
    }
    dominant_dimension = max(dimension_map, key=dimension_map.get)
    weakest_dimension = min(dimension_map, key=dimension_map.get)

    subject_counts = (
        ChatSession.objects
        .filter(user=request.user)
        .values("subject")
        .annotate(count=Count("id"))
    )
    subjects = [s["subject"] for s in subject_counts]
    subject_values = [s["count"] for s in subject_counts]

    curiosity_score = (
        ChatSession.objects
        .filter(user=request.user)
        .values("topic")
        .distinct()
        .count()
    )

    quiz_aggregate = QuizSession.objects.filter(
        user=request.user, completed=True
    ).aggregate(
        total_correct=Sum("score"),
        total_attempted=Sum("total_questions"),
    )
    total_correct = quiz_aggregate["total_correct"] or 0
    total_attempted = quiz_aggregate["total_attempted"] or 0
    quiz_accuracy = round(
        (total_correct / total_attempted * 100) if total_attempted > 0 else 0, 1
    )

    topics_mastered = TopicMastery.objects.filter(
        user=request.user,
        mastery_percentage__gte=80
    ).count()

    weekly_quiz_xp = list(
        QuizSession.objects
        .filter(user=request.user, completed=True)
        .order_by("date")
        .values_list("xp_earned", flat=True)[:7]
    )
    cumulative = 0
    weekly_growth = []
    for xp in weekly_quiz_xp:
        cumulative += xp
        weekly_growth.append(cumulative)
    if not weekly_growth:
        weekly_growth = [0]

    top_subjects = (
        ChatSession.objects
        .filter(user=request.user)
        .values("subject")
        .annotate(count=Count("id"))
        .order_by("-count")[:2]
    )
    top_topics = (
        ChatSession.objects
        .filter(user=request.user)
        .values("topic")
        .annotate(count=Count("id"))
        .order_by("-count")[:3]
    )
    subject_names = ", ".join(s["subject"] for s in top_subjects) or "various subjects"
    topic_names = ", ".join(t["topic"] for t in top_topics) or "multiple topics"

    insight_text = (
        f"Based on your SmartChat activity, you appear most interested in {subject_names}. "
        f"Topics you engage with frequently include {topic_names}. "
        f"Your strongest learning dimension is {dominant_dimension}, while {weakest_dimension} "
        f"has room to grow — try the daily quiz to strengthen it!"
    )

    return render(request, "analytics.html", {
        "profile": profile,
        "balance_score": balance_score,
        "subjects": subjects,
        "subject_values": subject_values,
        "dominant_dimension": dominant_dimension,
        "weakest_dimension": weakest_dimension,
        "curiosity_score": curiosity_score,
        "quiz_accuracy": quiz_accuracy,
        "topics_mastered": topics_mastered,
        "weekly_growth": weekly_growth,
        "insight_text": insight_text,
        "insight_disclaimer": (
            "These insights are based only on your interactions with SmartChat."
        ),
    })


# ─────────────────────────────────────────────────────────────
# Chat
# ─────────────────────────────────────────────────────────────

@login_required
def chat_home(request):
    # Redirect teachers to their own chat home — never show student chat list
    if request.user.role == "teacher":
        return redirect("teacher_chat_home")
    sessions = ChatSession.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "chat_home.html", {"sessions": sessions})


@login_required
def teacher_chat_home(request):
    if request.user.role != "teacher":
        return redirect("chat_home")
    sessions = (
        ChatSession.objects
        .filter(user=request.user)
        .order_by("-created_at")
    )
    return render(request, "teacher/chat_home.html", {"sessions": sessions})


@login_required
def teacher_create_session(request):
    """Teacher-specific session creation — redirects to teacher chat home on GET."""
    if request.user.role != "teacher":
        return redirect("chat_home")
    if request.method == "POST":
        topic   = request.POST.get("topic", "").strip()
        subject = request.POST.get("subject", "").strip()
        if not topic or not subject:
            sessions = ChatSession.objects.filter(user=request.user).order_by("-created_at")
            return render(request, "teacher/chat_home.html", {
                "sessions": sessions,
                "error": "Please fill in both subject and topic.",
            })
        session = ChatSession.objects.create(user=request.user, topic=topic, subject=subject)
        SessionNote.objects.create(session=session)
        intro_reply, _ = generate_session_intro(topic, standard=10)
        Message.objects.create(session=session, role="bot", content=intro_reply)
        return redirect("chat_room", session_id=session.id)
    return redirect("teacher_chat_home")


@login_required
def create_session(request):
    if request.method == "POST":
        topic = request.POST.get("topic")
        subject = request.POST.get("subject")

        session = ChatSession.objects.create(
            user=request.user,
            topic=topic,
            subject=subject,
        )
        SessionNote.objects.create(session=session)

        if request.user.role != "teacher":
            profile, _ = StudentProfile.objects.get_or_create(user=request.user)
            profile.xp_narrative += 5
            profile.calculate_total_xp()

        # Teachers have no standard — use a sensible default for voice
        standard = request.user.standard if request.user.standard else 10
        intro_reply, _dimension = generate_session_intro(topic, standard)

        Message.objects.create(
            session=session,
            role="bot",
            content=intro_reply,
        )

        return redirect("chat_room", session_id=session.id)


@login_required
def chat_room(request, session_id):
    session = ChatSession.objects.get(id=session_id, user=request.user)
    note = SessionNote.objects.get(session=session)
    profile = None
    if request.user.role != "teacher":
        profile, _ = StudentProfile.objects.get_or_create(user=request.user)

    quiz_session = None

    quiz_id = request.GET.get("quiz")
    if quiz_id:
        quiz_session = QuizSession.objects.filter(
            id=quiz_id, user=request.user
        ).first()

    if request.method == "POST":

        # ── SUBMIT QUIZ ───────────────────────────────────────
        # Score the quiz in-place and fall through to re-render the chat
        # room. The modal template detects quiz_session.completed and
        # shows results (correct/wrong highlights + explanations) inside
        # the same page — no redirect away from the chat room.
        if "submit_quiz" in request.POST:
            quiz_id_post = request.POST.get("quiz_id")
            if quiz_id_post:
                try:
                    qs = QuizSession.objects.get(id=quiz_id_post, user=request.user)
                except QuizSession.DoesNotExist:
                    qs = None

                if qs and not qs.completed:
                    score = 0
                    for question in qs.questions.all():
                        selected = request.POST.get(f"question_{question.id}")
                        question.selected_answer = selected
                        question.save()

                        if question.is_correct():
                            score += 1
                            if profile:
                                dim = (question.dimension or "LOGIC").upper()
                                if dim == "LOGIC":
                                    profile.xp_logic += 10
                                elif dim == "SYSTEMS":
                                    profile.xp_systems += 10
                                elif dim == "NARRATIVE":
                                    profile.xp_narrative += 10
                                elif dim == "SPATIAL":
                                    profile.xp_spatial += 10

                    if profile:
                        if score == qs.total_questions and score > 0:
                            profile.xp_logic += 20  # perfect-quiz bonus
                        profile.calculate_total_xp()

                    qs.score = score
                    qs.xp_earned = score * 10
                    qs.completed = True
                    qs.calculate_accuracy()
                    qs.save()

                    if qs.topic and qs.chat_session:
                        _update_topic_mastery(
                            user=request.user,
                            subject=qs.chat_session.subject,
                            topic=qs.topic,
                            total_questions=qs.total_questions,
                            correct_answers=score,
                        )

                # Put the now-completed quiz session into context so the
                # modal renders results on the same page.
                if qs:
                    quiz_session = qs

        if "test_me" in request.POST:
            last_bot_message = session.messages.filter(role="bot").last()

            if last_bot_message:
                quiz_data = generate_chat_quiz(
                    request.user.standard,
                    session.topic,
                    last_bot_message.content,
                )

                if quiz_data:
                    quiz_session = QuizSession.objects.create(
                        user=request.user,
                        quiz_type="chat",
                        chat_session=session,
                        topic=session.topic,
                        total_questions=len(quiz_data),
                    )

                    for q in quiz_data:
                        if not isinstance(q, dict):
                            continue

                        options    = q.get("options", {})
                        solution   = q.get("solution", "")
                        why_correct = q.get("why_correct", "")
                        why_wrong  = q.get("why_wrong", {})

                        # If Gemini only returned "solution" (old prompt format),
                        # copy it into why_correct so the card always has content.
                        if not why_correct and solution and isinstance(solution, str):
                            why_correct = solution

                        explanation_data = {
                            "solution":    solution,
                            "why_correct": why_correct,
                            "why_wrong":   why_wrong if isinstance(why_wrong, dict) else {},
                            "hint":        q.get("hint", ""),
                        }

                        QuizQuestion.objects.create(
                            session=quiz_session,
                            question_text=q.get("question", ""),
                            option_a=options.get("A", ""),
                            option_b=options.get("B", ""),
                            option_c=options.get("C", ""),
                            option_d=options.get("D", ""),
                            correct_answer=q.get("correct_answer", ""),
                            dimension=q.get("dimension", "LOGIC"),
                            explanation=_safe_explanation_json(explanation_data),
                        )

        # ── CHAT MESSAGE ──────────────────────────────────────
        # Regular student/teacher message — generate AI response.
        # Handled last so submit_quiz and test_me take priority.
        if "message" in request.POST:
            user_message = request.POST.get("message", "").strip()
            if user_message:
                # Save the user message
                Message.objects.create(
                    session=session,
                    role="user",
                    content=user_message,
                )

                # Build conversation history for context.
                # list() converts the QuerySet so build_history can use [-4:] safely.
                conversation = list(session.messages.all().order_by("created_at"))

                # Classify XP dimension from the message
                from .gemini_service import classify_dimension
                dimension = classify_dimension(user_message)

                # Award XP for engagement
                if profile:
                    if dimension == "LOGIC":
                        profile.xp_logic += 5
                    elif dimension == "SYSTEMS":
                        profile.xp_systems += 5
                    elif dimension == "NARRATIVE":
                        profile.xp_narrative += 5
                    elif dimension == "SPATIAL":
                        profile.xp_spatial += 5
                    profile.calculate_total_xp()

                standard = request.user.standard if request.user.standard else 10
                role = "teacher" if request.user.role == "teacher" else "student"

                ai_reply, _ = generate_ai_response(
                    conversation=conversation,
                    standard=standard,
                    subject=session.subject,
                    topic=session.topic,
                    role=role,
                )

                Message.objects.create(
                    session=session,
                    role="bot",
                    content=ai_reply,
                )

                return redirect("chat_room", session_id=session.id)

    raw_messages = session.messages.all().order_by("created_at")
    formatted_messages = []
    for msg in raw_messages:
        if msg.role == "bot":
            msg.content = markdown.markdown(
                msg.content, extensions=["fenced_code", "tables"]
            )
        formatted_messages.append(msg)

    template = "teacher/chat_room.html" if request.user.role == "teacher" else "chat_room.html"
    return render(request, template, {
        "session": session,
        "messages": formatted_messages,
        "note": note,
        "quiz_session": quiz_session,
    })


@login_required
def save_note(request, session_id):
    session = ChatSession.objects.get(id=session_id, user=request.user)
    note = SessionNote.objects.get(session=session)

    if request.method == "POST":
        content = request.POST.get("content", "")
        note.content = content
        note.save()

    return redirect("chat_room", session_id=session.id)


# ─────────────────────────────────────────────────────────────
# Quiz
# ─────────────────────────────────────────────────────────────

@login_required
def daily_quiz(request):
    today = timezone.now().date()

    session = QuizSession.objects.filter(
        user=request.user, date=today, quiz_type="daily"
    ).first()

    if not session:
        profile, _ = StudentProfile.objects.get_or_create(user=request.user)

        dimension_map = {
            "LOGIC": profile.xp_logic,
            "SYSTEMS": profile.xp_systems,
            "NARRATIVE": profile.xp_narrative,
            "SPATIAL": profile.xp_spatial,
        }
        weakest_dimension = min(dimension_map, key=dimension_map.get)

        session = QuizSession.objects.create(
            user=request.user,
            quiz_type="daily",
            topic=f"Daily {weakest_dimension.capitalize()} Challenge",
        )

        quiz_data = generate_daily_quiz(request.user.standard, weakest_dimension)

        for q in quiz_data:
            options     = q.get("options", {})
            solution    = q.get("solution", "")
            why_correct = q.get("why_correct", "")
            why_wrong   = q.get("why_wrong", {})
            # Fallback: if why_correct missing, use solution
            if not why_correct and solution and isinstance(solution, str):
                why_correct = solution
            QuizQuestion.objects.create(
                session=session,
                question_text=q.get("question", ""),
                option_a=options.get("A", ""),
                option_b=options.get("B", ""),
                option_c=options.get("C", ""),
                option_d=options.get("D", ""),
                correct_answer=q.get("correct_answer", ""),
                dimension=weakest_dimension,
                explanation=_safe_explanation_json({
                    "solution":    solution or why_correct,
                    "why_correct": why_correct,
                    "why_wrong":   why_wrong if isinstance(why_wrong, dict) else {},
                    "hint":        q.get("hint", ""),
                }),
            )

    return render(request, "daily_quiz.html", {"session": session})


@login_required
def submit_quiz(request, session_id):
    session = QuizSession.objects.get(id=session_id, user=request.user)
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)

    score = 0

    for question in session.questions.all():
        selected = request.POST.get(f"question_{question.id}")
        question.selected_answer = selected
        question.save()

        if question.is_correct():
            score += 1
            dim = (question.dimension or "LOGIC").upper()
            if dim == "LOGIC":
                profile.xp_logic += 10
            elif dim == "SYSTEMS":
                profile.xp_systems += 10
            elif dim == "NARRATIVE":
                profile.xp_narrative += 10
            elif dim == "SPATIAL":
                profile.xp_spatial += 10

    if score == session.total_questions and score > 0:
        profile.xp_logic += 20

    today = timezone.now().date()
    if session.quiz_type == "daily":
        profile.xp_spatial += 10
        if profile.last_quiz_date:
            from datetime import timedelta
            if profile.last_quiz_date == today - timedelta(days=1):
                profile.streak_count += 1
                profile.xp_spatial += 5 * profile.streak_count
            elif profile.last_quiz_date < today - timedelta(days=1):
                profile.streak_count = 1
        else:
            profile.streak_count = 1
        profile.last_quiz_date = today

    session.score = score
    session.xp_earned = score * 10
    session.completed = True
    session.calculate_accuracy()
    session.save()

    profile.calculate_total_xp()

    if session.topic and session.chat_session:
        _update_topic_mastery(
            user=request.user,
            subject=session.chat_session.subject,
            topic=session.topic,
            total_questions=session.total_questions,
            correct_answers=score,
        )

    return redirect("quiz_result", session_id=session.id)


@login_required
def take_quiz(request, session_id):
    session = QuizSession.objects.get(id=session_id, user=request.user)

    if request.method == "POST":
        return submit_quiz(request, session_id)

    return render(request, "daily_quiz.html", {"session": session})


@login_required
def quiz_result(request, session_id):
    session = QuizSession.objects.get(id=session_id, user=request.user)
    questions = session.questions.all()

    return render(request, "quiz_result.html", {
        "session": session,
        "questions": questions,
        "score": session.score,
        "xp_earned": session.xp_earned,
    })


# ─────────────────────────────────────────────────────────────
# Teacher Views
# ─────────────────────────────────────────────────────────────

@login_required
def teacher_dashboard(request):
    if request.user.role != "teacher":
        return redirect("student_dashboard")

    standards = (
        CustomUser.objects
        .filter(
            role="student",
            school_name=request.user.school_name,
            standard__isnull=False,
        )
        .values_list("standard", flat=True)
        .distinct()
        .order_by("standard")
    )

    return render(request, "teacher/dashboard.html", {"standards": standards})


@login_required
def teacher_divisions(request, standard):
    divisions = (
        CustomUser.objects
        .filter(role="student", standard=standard)
        .exclude(division__isnull=True)
        .exclude(division__exact="")
        .values_list("division", flat=True)
        .distinct()
        .order_by("division")
    )

    return render(request, "teacher/divisions.html", {
        "standard": standard,
        "divisions": divisions,
    })


@login_required
def teacher_division_dashboard(request, standard, division):
    if request.user.role != "teacher":
        return redirect("student_dashboard")

    students = StudentProfile.objects.filter(
        user__role="student",
        user__school_name=request.user.school_name,
        user__standard=standard,
        user__division=division,
    )

    total_students = students.count()
    if total_students == 0:
        return redirect("teacher_dashboard")

    aggregates = students.aggregate(
        avg_logic=Avg("xp_logic"),
        avg_systems=Avg("xp_systems"),
        avg_narrative=Avg("xp_narrative"),
        avg_spatial=Avg("xp_spatial"),
        avg_xp=Avg("total_xp"),
    )

    avg_logic     = round(aggregates["avg_logic"]     or 0, 1)
    avg_systems   = round(aggregates["avg_systems"]   or 0, 1)
    avg_narrative = round(aggregates["avg_narrative"] or 0, 1)
    avg_spatial   = round(aggregates["avg_spatial"]   or 0, 1)
    avg_xp        = round(aggregates["avg_xp"]        or 0, 1)

    dimension_map = {
        "Logic": avg_logic,
        "Systems": avg_systems,
        "Narrative": avg_narrative,
        "Spatial": avg_spatial,
    }
    has_dimension_data  = any(v > 0 for v in dimension_map.values())
    strongest_dimension = max(dimension_map, key=dimension_map.get) if has_dimension_data else None
    weakest_dimension   = min(dimension_map, key=dimension_map.get) if has_dimension_data else None

    topic_difficulty = _compute_topic_difficulty(
        school_name=request.user.school_name,
        standard=standard,
        division=division,
    )

    subject_engagement_qs = (
        ChatSession.objects
        .filter(
            user__school_name=request.user.school_name,
            user__standard=standard,
            user__division=division,
        )
        .values("subject")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    subject_engagement = list(subject_engagement_qs)

    total_sessions = sum(s["count"] for s in subject_engagement)
    engagement_score = round(total_sessions / total_students, 1) if total_sessions > 0 else None

    # Learning style breakdown — dominant dimension per student
    learning_styles = {"Logic": 0, "Systems": 0, "Narrative": 0, "Spatial": 0}
    for sp in students.values("xp_logic", "xp_systems", "xp_narrative", "xp_spatial"):
        dm = {
            "Logic":     sp["xp_logic"],
            "Systems":   sp["xp_systems"],
            "Narrative": sp["xp_narrative"],
            "Spatial":   sp["xp_spatial"],
        }
        best = max(dm, key=dm.get)
        # students with no XP data at all count as Narrative (new student)
        if dm[best] == 0:
            learning_styles["Narrative"] += 1
        else:
            learning_styles[best] += 1

    has_learning_styles = any(v > 0 for v in learning_styles.values())

    leaderboard = sorted(
        students.select_related("user"),
        key=lambda p: p.leaderboard_score,
        reverse=True,
    )

    return render(request, "teacher/division_dashboard.html", {
        "standard":            standard,
        "division":            division,
        "students":            leaderboard,
        "total_students":      total_students,
        "avg_xp":              avg_xp,
        "avg_logic":           avg_logic,
        "avg_systems":         avg_systems,
        "avg_narrative":       avg_narrative,
        "avg_spatial":         avg_spatial,
        "has_dimension_data":  has_dimension_data,
        "strongest_dimension": strongest_dimension,
        "weakest_dimension":   weakest_dimension,
        "topic_difficulty":    topic_difficulty,
        "subject_engagement":  subject_engagement,
        "engagement_score":    engagement_score,
        "has_engagement":      engagement_score is not None,
        "learning_styles":     learning_styles,
        "has_learning_styles": has_learning_styles,
    })


@login_required
def teacher_school_dashboard(request):
    if request.user.role != "teacher":
        return redirect("student_dashboard")

    students = StudentProfile.objects.filter(
        user__role="student",
        user__school_name=request.user.school_name,
    )

    total_students = students.count()

    if total_students == 0:
        return render(request, "teacher/school_dashboard.html", {
            "total_students":      0,
            "has_dimension_data":  False,
            "has_learning_styles": False,
            "engagement_score":    None,
            "has_engagement":      False,
            "unique_topics_count": 0,
        })

    aggregates = students.aggregate(
        avg_logic=Avg("xp_logic"),
        avg_systems=Avg("xp_systems"),
        avg_narrative=Avg("xp_narrative"),
        avg_spatial=Avg("xp_spatial"),
        total_school_xp=Sum("total_xp"),
    )

    avg_logic       = round(aggregates["avg_logic"]     or 0, 1)
    avg_systems     = round(aggregates["avg_systems"]   or 0, 1)
    avg_narrative   = round(aggregates["avg_narrative"] or 0, 1)
    avg_spatial     = round(aggregates["avg_spatial"]   or 0, 1)
    total_school_xp = aggregates["total_school_xp"] or 0

    dimension_map = {
        "Logic": avg_logic,
        "Systems": avg_systems,
        "Narrative": avg_narrative,
        "Spatial": avg_spatial,
    }
    has_dimension_data  = any(v > 0 for v in dimension_map.values())
    strongest_dimension = max(dimension_map, key=dimension_map.get) if has_dimension_data else None
    weakest_dimension   = min(dimension_map, key=dimension_map.get) if has_dimension_data else None

    avg_xp = round(total_school_xp / total_students, 1) if total_students else 0

    subject_engagement_qs = (
        ChatSession.objects
        .filter(user__school_name=request.user.school_name)
        .values("subject")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    subject_engagement = list(subject_engagement_qs)

    total_sessions = sum(s["count"] for s in subject_engagement)
    engagement_score = round(total_sessions / total_students, 1) if total_sessions > 0 else None

    unique_topics_count = (
        ChatSession.objects
        .filter(user__school_name=request.user.school_name)
        .values("topic")
        .distinct()
        .count()
    )

    topic_difficulty = _compute_topic_difficulty(
        school_name=request.user.school_name
    )

    learning_styles = {"Logic": 0, "Systems": 0, "Narrative": 0, "Spatial": 0}
    for sp in students.values("xp_logic", "xp_systems", "xp_narrative", "xp_spatial"):
        dm = {
            "Logic":     sp["xp_logic"],
            "Systems":   sp["xp_systems"],
            "Narrative": sp["xp_narrative"],
            "Spatial":   sp["xp_spatial"],
        }
        best = max(dm, key=dm.get)
        if dm[best] == 0:
            learning_styles["Narrative"] += 1
        else:
            learning_styles[best] += 1

    has_learning_styles = any(v > 0 for v in learning_styles.values())

    return render(request, "teacher/school_dashboard.html", {
        "total_students":      total_students,
        "avg_xp":              avg_xp,
        "avg_logic":           avg_logic,
        "avg_systems":         avg_systems,
        "avg_narrative":       avg_narrative,
        "avg_spatial":         avg_spatial,
        "has_dimension_data":  has_dimension_data,
        "strongest_dimension": strongest_dimension,
        "weakest_dimension":   weakest_dimension,
        "total_school_xp":     total_school_xp,
        "subject_engagement":  subject_engagement,
        "engagement_score":    engagement_score,
        "has_engagement":      engagement_score is not None,
        "unique_topics_count": unique_topics_count,
        "topic_difficulty":    topic_difficulty,
        "learning_styles":     learning_styles,
        "has_learning_styles": has_learning_styles,
    })


@login_required
def teacher_student_report(request, user_id):
    if request.user.role != "teacher":
        return redirect("student_dashboard")

    student = get_object_or_404(CustomUser, id=user_id, role="student")
    profile = get_object_or_404(StudentProfile, user=student)

    topic_masteries = TopicMastery.objects.filter(user=student).order_by("-mastery_percentage")

    curiosity_score = (
        ChatSession.objects
        .filter(user=student)
        .values("topic")
        .distinct()
        .count()
    )

    quiz_aggregate = QuizSession.objects.filter(
        user=student, completed=True
    ).aggregate(
        total_correct=Sum("score"),
        total_attempted=Sum("total_questions"),
    )
    total_correct   = quiz_aggregate["total_correct"]   or 0
    total_attempted = quiz_aggregate["total_attempted"] or 0
    quiz_accuracy = round(
        (total_correct / total_attempted * 100) if total_attempted > 0 else 0, 1
    )

    topics_mastered = topic_masteries.filter(mastery_percentage__gte=80).count()

    has_xp_data = any([
        profile.xp_logic,
        profile.xp_systems,
        profile.xp_narrative,
        profile.xp_spatial,
    ])

    return render(request, "teacher/student_report.html", {
        "student":         student,
        "profile":         profile,
        "topic_masteries": topic_masteries,
        "curiosity_score": curiosity_score,
        "quiz_accuracy":   quiz_accuracy,
        "topics_mastered": topics_mastered,
        "has_xp_data":     has_xp_data,
    })


@login_required
def teacher_performance_trends(request):
    if request.user.role != "teacher":
        return redirect("student_dashboard")

    students = StudentProfile.objects.filter(
        user__role="student",
        user__school_name=request.user.school_name,
    )

    aggregate = students.aggregate(total_xp=Sum("total_xp"))
    total_xp = aggregate["total_xp"] or 0

    return render(request, "teacher/performance_trends.html", {
        "total_xp": total_xp,
    })



# ─────────────────────────────────────────────────────────────
# Brain Gym — Daily Interactive Quizzes
# ─────────────────────────────────────────────────────────────

from django.http import JsonResponse

@login_required
def brain_gym_quiz(request, category):
    """
    AJAX endpoint called by the Brain Gym cards on the student dashboard.

    Flow:
      1. Check if student already has a Brain Gym quiz of this category today
         (so clicking a card twice doesn't regenerate the quiz).
      2. If not, call brain_gym_service to generate 3 questions via AI.
      3. Save into QuizSession + QuizQuestion, identical schema to daily_quiz.
      4. Return {session_id} as JSON — JS then redirects to take_quiz page.

    Returns JSON: {"session_id": <int>} on success
                  {"error": "<msg>"}    on failure (HTTP 400 / 500)
    """
    if request.user.role == "teacher":
        return JsonResponse({"error": "Brain Gym is for students only."}, status=403)

    today = timezone.now().date()
    quiz_type_key = f"brain_gym_{category}"

    # Re-use today's session if it exists (idempotent)
    existing = QuizSession.objects.filter(
        user=request.user,
        quiz_type=quiz_type_key,
        date=today,
    ).first()

    if existing:
        return JsonResponse({"session_id": existing.id})

    # Generate fresh quiz
    standard = request.user.standard or 8
    questions = generate_brain_gym_quiz(category, standard)

    if not questions:
        return JsonResponse(
            {"error": "Could not generate quiz right now. Please try again in a moment."},
            status=500,
        )

    # Find dimension from category metadata
    from .brain_gym_service import BRAIN_GYM_CATEGORIES
    cat_meta  = next((c for c in BRAIN_GYM_CATEGORIES if c["key"] == category), {})
    dimension = cat_meta.get("dimension", "NARRATIVE")
    label     = cat_meta.get("label", category.upper())

    session = QuizSession.objects.create(
        user=request.user,
        quiz_type=quiz_type_key,
        topic=f"Brain Gym: {label}",
        total_questions=len(questions),
    )

    for q in questions:
        options   = q.get("options", {})
        solution    = q.get("solution", "")
        why_correct = q.get("why_correct", "")
        why_wrong   = q.get("why_wrong", {})
        if not why_correct and solution and isinstance(solution, str):
            why_correct = solution

        QuizQuestion.objects.create(
            session=session,
            question_text=q.get("question", ""),
            option_a=options.get("A", ""),
            option_b=options.get("B", ""),
            option_c=options.get("C", ""),
            option_d=options.get("D", ""),
            correct_answer=q.get("correct_answer", "A"),
            dimension=q.get("dimension", dimension),
            explanation=_safe_explanation_json({
                "solution":    solution or why_correct,
                "why_correct": why_correct,
                "why_wrong":   why_wrong if isinstance(why_wrong, dict) else {},
                "hint":        q.get("hint", ""),
            }),
        )

    return JsonResponse({"session_id": session.id})

# ─────────────────────────────────────────────────────────────
# Internal Helpers


def _safe_explanation_json(data: dict) -> str:
    """
    Serialize explanation dict to JSON that is safe to embed inside a
    <script type="application/json"> tag.

    The only character sequence that can break a script tag is </script>
    (or </Script> etc.) — we escape the slash to prevent it.
    Using ensure_ascii=False keeps non-ASCII characters readable.
    """
    raw = json.dumps(data, ensure_ascii=False)
    # Escape any </script> sequence so it can't break the script tag
    raw = raw.replace("</", "<\/")
    return raw


# ─────────────────────────────────────────────────────────────

def _update_topic_mastery(user, subject, topic, total_questions, correct_answers):
    mastery, _ = TopicMastery.objects.get_or_create(
        user=user,
        subject=subject,
        topic=topic,
    )
    mastery.total_questions += total_questions
    mastery.correct_answers += correct_answers
    mastery.save()


def _compute_topic_difficulty(school_name, standard=None, division=None):
    """
    Topic difficulty = chat sessions on a topic
                     + incorrect quiz answers on that topic.
    Returns [{topic, difficulty_score}, ...] ordered desc, max 10.
    """
    chat_filter = Q(user__school_name=school_name)
    if standard:
        chat_filter &= Q(user__standard=standard)
    if division:
        chat_filter &= Q(user__division=division)

    chat_counts = (
        ChatSession.objects
        .filter(chat_filter)
        .values("topic")
        .annotate(chat_count=Count("id"))
    )

    topic_scores = {entry["topic"]: entry["chat_count"] for entry in chat_counts}

    quiz_filter = Q(user__school_name=school_name, completed=True)
    if standard:
        quiz_filter &= Q(user__standard=standard)
    if division:
        quiz_filter &= Q(user__division=division)

    quiz_sessions = QuizSession.objects.filter(quiz_filter).select_related("chat_session")
    for qs in quiz_sessions:
        topic = qs.topic or (qs.chat_session.topic if qs.chat_session else None)
        if not topic:
            continue
        incorrect = qs.total_questions - qs.score
        topic_scores[topic] = topic_scores.get(topic, 0) + incorrect

    result = [
        {"topic": t, "difficulty_score": s}
        for t, s in topic_scores.items()
    ]
    result.sort(key=lambda x: x["difficulty_score"], reverse=True)
    return result[:10]