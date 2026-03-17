from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils import timezone


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('teacher', 'Teacher'),
    )

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    standard = models.IntegerField(null=True, blank=True)
    division = models.CharField(max_length=5, null=True, blank=True)
    school_name = models.CharField(max_length=255, null=True, blank=True)
    roll_number = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return self.username


class StudentProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)

    # XP Dimensions
    # xp_logic     → Problem Solving Ability
    # xp_systems   → Analytical Thinking
    # xp_narrative → Conceptual Understanding
    # xp_spatial   → Learning Consistency
    xp_logic = models.IntegerField(default=0)
    xp_systems = models.IntegerField(default=0)
    xp_narrative = models.IntegerField(default=0)
    xp_spatial = models.IntegerField(default=0)

    total_xp = models.IntegerField(default=0)
    streak_count = models.IntegerField(default=0)
    last_quiz_date = models.DateField(null=True, blank=True)

    def calculate_total_xp(self):
        self.total_xp = (
            self.xp_logic +
            self.xp_systems +
            self.xp_narrative +
            self.xp_spatial
        )
        self.save()

    @property
    def leaderboard_score(self):
        """Composite score: total XP + streak bonus."""
        return self.total_xp + (self.streak_count * 10)

    def __str__(self):
        return f"{self.user.username} Profile"


class ChatSession(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    topic = models.CharField(max_length=200)
    subject = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    # Track how many questions the student asked (curiosity signal)
    questions_asked = models.IntegerField(default=0)

    # Track how well the student engaged with this topic
    mastery_score = models.FloatField(default=0.0)

    def __str__(self):
        return f"{self.user.username} - {self.topic}"


class Message(models.Model):
    ROLE_CHOICES = (
        ('user', 'User'),
        ('bot', 'Bot'),
    )

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.role} - {self.session.topic}"


class SessionNote(models.Model):
    session = models.OneToOneField(ChatSession, on_delete=models.CASCADE)
    content = models.TextField(blank=True)

    def __str__(self):
        return f"Notes - {self.session.topic}"


class TopicMastery(models.Model):
    """
    Tracks a student's mastery level per subject+topic.
    Updated after every quiz submission related to that topic.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="topic_masteries"
    )
    subject = models.CharField(max_length=100)
    topic = models.CharField(max_length=200)

    total_questions = models.IntegerField(default=0)
    correct_answers = models.IntegerField(default=0)

    # mastery_percentage = correct_answers / total_questions * 100
    mastery_percentage = models.FloatField(default=0.0)

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "subject", "topic")
        verbose_name_plural = "Topic Masteries"

    def recalculate(self):
        if self.total_questions > 0:
            self.mastery_percentage = round(
                (self.correct_answers / self.total_questions) * 100, 2
            )
        else:
            self.mastery_percentage = 0.0

    def save(self, *args, **kwargs):
        self.recalculate()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} | {self.subject} | {self.topic} | {self.mastery_percentage:.1f}%"


class QuizSession(models.Model):

    QUIZ_TYPE_CHOICES = (
        ("chat", "Chat Based"),
        ("daily", "Daily Weak Dimension"),
        ("gk", "General Awareness"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    quiz_type = models.CharField(
        max_length=20,
        choices=QUIZ_TYPE_CHOICES,
        default="daily"
    )

    # Only used when quiz is generated from chat
    chat_session = models.ForeignKey(
        ChatSession,
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )

    # Only used for GK category (sports, news, etc.)
    category = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )

    # Topic this quiz covers (for TopicMastery updates)
    topic = models.CharField(max_length=200, null=True, blank=True)

    date = models.DateField(default=timezone.now)
    score = models.IntegerField(default=0)
    total_questions = models.IntegerField(default=5)
    xp_earned = models.IntegerField(default=0)
    completed = models.BooleanField(default=False)

    # accuracy = score / total_questions (stored for fast querying)
    accuracy = models.FloatField(default=0.0)

    def calculate_accuracy(self):
        if self.total_questions > 0:
            self.accuracy = round(self.score / self.total_questions, 4)
        else:
            self.accuracy = 0.0

    def __str__(self):
        return f"{self.user.username} - {self.quiz_type} - {self.date}"


class QuizQuestion(models.Model):
    session = models.ForeignKey(
        QuizSession,
        on_delete=models.CASCADE,
        related_name="questions"
    )

    question_text = models.TextField()

    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)

    correct_answer = models.CharField(max_length=1)
    selected_answer = models.CharField(max_length=1, null=True, blank=True)

    dimension = models.CharField(max_length=20, null=True, blank=True)

    explanation = models.TextField(null=True, blank=True)

    def is_correct(self):
        return self.selected_answer == self.correct_answer