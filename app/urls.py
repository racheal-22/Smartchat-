from django.urls import path
from . import views

urlpatterns = [

    path('', views.landing_page, name='landing'),
    path('login/', views.login_view, name='login'),
    path("signup/student/", views.student_signup, name="student_signup"),
    path("signup/teacher/", views.teacher_signup, name="teacher_signup"),

    # ── Student ──────────────────────────────────────────────
    path('dashboard/', views.student_dashboard, name='student_dashboard'),
    path('analytics/', views.analytics_view, name='analytics'),

    # ── Chat (shared session room, template switches by role) ─
    path('chat/', views.chat_home, name='chat_home'),
    path('chat/new/', views.create_session, name='create_session'),
    path('chat/<int:session_id>/', views.chat_room, name='chat_room'),
    path('chat/<int:session_id>/save-note/', views.save_note, name='save_note'),

    # ── Quiz ─────────────────────────────────────────────────
    path("quiz/", views.daily_quiz, name="daily_quiz"),
    path("quiz/submit/<int:session_id>/", views.submit_quiz, name="submit_quiz"),
    path("quiz/result/<int:session_id>/", views.quiz_result, name="quiz_result"),
    path("quiz/<int:session_id>/take/", views.take_quiz, name="take_quiz"),

    # ── Teacher analytics ────────────────────────────────────
    path("teacher/dashboard/", views.teacher_school_dashboard, name="teacher_school_dashboard"),
    path("teacher/", views.teacher_dashboard, name="teacher_dashboard"),
    path("teacher/student/<int:user_id>/", views.teacher_student_report, name="teacher_student_report"),
    path("teacher/trends/", views.teacher_performance_trends, name="teacher_trends"),
    path("teacher/<int:standard>/", views.teacher_divisions, name="teacher_divisions"),
    path("teacher/<int:standard>/<str:division>/", views.teacher_division_dashboard, name="teacher_division_dashboard"),

    # ── Teacher AI chat ──────────────────────────────────────
    # Separate URL namespace so teachers never see the student chat list.
    # chat_home redirects teachers here automatically.
    path("teacher/chat/", views.teacher_chat_home, name="teacher_chat_home"),
    path("teacher/chat/new/", views.teacher_create_session, name="teacher_create_session"),

    # ── Brain Gym ────────────────────────────────────────────
    # AJAX endpoint: returns {session_id} to open quiz in take_quiz view
    path("brain-gym/<str:category>/", views.brain_gym_quiz, name="brain_gym_quiz"),

    # ── Shared ───────────────────────────────────────────────
    path("logout/", views.logout_view, name="logout"),
]