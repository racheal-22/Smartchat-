"""
Management command: generate_brain_gym
=======================================
Pre-generates Brain Gym quizzes for all active students so the first
click on any card gets an instant response (no AI wait time).

File location: app/management/commands/generate_brain_gym.py

Also create these empty files if they don't exist:
  app/management/__init__.py
  app/management/commands/__init__.py

Run daily via cron or Windows Task Scheduler:

    Linux (daily at 6 AM):
    0 6 * * * /path/to/venv/bin/python manage.py generate_brain_gym

    Windows Task Scheduler:
    Program  : C:\\path\\to\\venv\\Scripts\\python.exe
    Arguments: manage.py generate_brain_gym

Usage:
    python manage.py generate_brain_gym               # all students, all categories
    python manage.py generate_brain_gym --category news   # one category only
    python manage.py generate_brain_gym --dry-run         # simulate, no DB writes
"""

import json
import traceback

from django.core.management.base import BaseCommand
from django.utils import timezone

from app.models import CustomUser, QuizSession, QuizQuestion
from app.brain_gym_service import generate_brain_gym_quiz, BRAIN_GYM_CATEGORIES


def _safe_explanation_json(data: dict) -> str:
    """
    Inline copy — avoids circular imports from app.views.
    Serialises explanation dict to JSON safe for embedding in script tags.
    """
    raw = json.dumps(data, ensure_ascii=False)
    raw = raw.replace("</", "<\\/")
    return raw


class Command(BaseCommand):
    help = "Pre-generate Daily Brain Gym quizzes for all active students."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate without saving anything to the database.",
        )
        parser.add_argument(
            "--category",
            type=str,
            default=None,
            help="Only generate for one category key, e.g. 'news'.",
        )

    def handle(self, *args, **options):
        dry_run  = options["dry_run"]
        only_cat = options["category"]
        today    = timezone.now().date()

        students   = CustomUser.objects.filter(role="student", is_active=True)
        categories = [
            c for c in BRAIN_GYM_CATEGORIES
            if not only_cat or c["key"] == only_cat
        ]

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n   Daily Brain Gym Generator - {today}"
                f"\n   Students  : {students.count()}"
                f"\n   Categories: {[c['key'] for c in categories]}"
                f"\n   Dry run   : {dry_run}\n"
            )
        )

        total_created = 0
        total_skipped = 0
        total_errors  = 0

        for category in categories:
            key   = category["key"]
            label = category["label"]
            dim   = category["dimension"]

            self.stdout.write(f"  Generating {label}...")

            try:
                questions = generate_brain_gym_quiz(key, standard=8)
            except Exception:
                self.stdout.write(self.style.ERROR(f"    Failed for {key}"))
                traceback.print_exc()
                total_errors += students.count()
                continue

            if not questions:
                self.stdout.write(
                    self.style.WARNING(f"    No questions returned for {key} - skipping")
                )
                total_errors += students.count()
                continue

            self.stdout.write(f"    Got {len(questions)} questions. Saving per student...")

            for student in students:
                quiz_type_key = f"brain_gym_{key}"

                if QuizSession.objects.filter(
                    user=student,
                    quiz_type=quiz_type_key,
                    date=today,
                ).exists():
                    total_skipped += 1
                    continue

                if dry_run:
                    total_created += 1
                    continue

                try:
                    session = QuizSession.objects.create(
                        user=student,
                        quiz_type=quiz_type_key,
                        topic=f"Brain Gym: {label}",
                        total_questions=len(questions),
                        date=today,
                    )

                    for q in questions:
                        opts        = q.get("options", {})
                        solution    = q.get("solution", "")
                        why_correct = q.get("why_correct", "")
                        why_wrong   = q.get("why_wrong", {})

                        if not why_correct and solution and isinstance(solution, str):
                            why_correct = solution

                        QuizQuestion.objects.create(
                            session=session,
                            question_text=q.get("question", ""),
                            option_a=opts.get("A", ""),
                            option_b=opts.get("B", ""),
                            option_c=opts.get("C", ""),
                            option_d=opts.get("D", ""),
                            correct_answer=q.get("correct_answer", "A"),
                            dimension=q.get("dimension", dim),
                            explanation=_safe_explanation_json({
                                "solution":    solution or why_correct,
                                "why_correct": why_correct,
                                "why_wrong":   why_wrong if isinstance(why_wrong, dict) else {},
                                "hint":        q.get("hint", ""),
                            }),
                        )

                    total_created += 1

                except Exception:
                    self.stdout.write(
                        self.style.ERROR(f"      Failed for {student.username}")
                    )
                    total_errors += 1

        action = "Would create" if dry_run else "Created"
        self.stdout.write(
            self.style.SUCCESS(
                f"\n  Done."
                f"\n   {action}  : {total_created}"
                f"\n   Skipped (already exists today): {total_skipped}"
                f"\n   Errors  : {total_errors}\n"
            )
        )