from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.urls import get_resolver

FORBIDDEN_APP_FRAGMENTS = [
    "celery",
    "redis",
    "pgvector",
    "vector",
    "embedding",
    "social",
    "subscription",
    "coupon",
    "credit",
    "team_billing",
    "notification",
    "calendar",
]

FORBIDDEN_MODEL_NAMES = {
    "CareerGraph",
    "Organization",
    "Team",
    "Subscription",
    "CreditBalance",
    "CoachMarketplace",
    "NotificationSchedule",
    "CalendarIntegration",
    "VectorEmbedding",
    "PromptEvalRun",
    "AudioPracticeAttempt",
    "VideoPracticeAttempt",
}

FORBIDDEN_ROUTE_FRAGMENTS = [
    "social",
    "oauth",
    "subscription",
    "coupon",
    "credit",
    "team-billing",
    "vector",
    "audio",
    "video",
    "notification",
    "calendar",
]

FORBIDDEN_DEPENDENCY_NAMES = {
    "celery",
    "redis",
    "pgvector",
    "django-allauth",
    "social-auth-app-django",
    "stripe",
}

FORBIDDEN_UI_FRAGMENTS = [
    "social login",
    "oauth",
    "subscription",
    "coupon",
    "credits",
    "team billing",
    "vector search",
    "audio practice",
    "video practice",
    "calendar sync",
]

TEXT_FILE_SUFFIXES = {".html", ".txt", ".md", ".py"}


@pytest.mark.django_db
def test_stage_5c_does_not_install_deferred_apps_or_models():
    installed = {app.lower() for app in settings.INSTALLED_APPS}
    for fragment in FORBIDDEN_APP_FRAGMENTS:
        assert not any(fragment in app for app in installed), fragment

    model_names = {model.__name__ for model in apps.get_models()}
    assert FORBIDDEN_MODEL_NAMES.isdisjoint(model_names)


def test_stage_5c_does_not_add_deferred_routes():
    def flatten(patterns):
        for pattern in patterns:
            yield str(pattern.pattern)
            if hasattr(pattern, "url_patterns"):
                yield from flatten(pattern.url_patterns)

    route_text = "\n".join(flatten(get_resolver().url_patterns)).lower()
    for fragment in FORBIDDEN_ROUTE_FRAGMENTS:
        assert fragment not in route_text, fragment


def test_stage_5c_does_not_declare_deferred_dependencies_or_settings():
    pyproject_text = Path("pyproject.toml").read_text().lower()
    for package in FORBIDDEN_DEPENDENCY_NAMES:
        assert package not in pyproject_text, package

    installed = "\n".join(settings.INSTALLED_APPS).lower()
    configured = "\n".join(dir(settings)).lower()
    for fragment in ["celery", "redis", "pgvector", "social_auth", "allauth"]:
        assert fragment not in installed
        assert fragment not in configured


def test_stage_5c_does_not_expose_deferred_user_interface_or_commands():
    scanned_paths = [
        *Path("templates").rglob("*"),
        *Path("apps").glob("*/templates/**/*"),
        *Path("apps").glob("*/management/commands/*.py"),
    ]
    for path in scanned_paths:
        if not path.is_file() or path.suffix not in TEXT_FILE_SUFFIXES:
            continue
        text = path.read_text(errors="ignore").lower()
        for fragment in FORBIDDEN_UI_FRAGMENTS:
            assert fragment not in text, f"{fragment} in {path}"


def test_stage_5c_validation_added_no_migrations():
    stage_migrations = [
        path for path in Path("apps").glob("*/migrations/*.py") if "stage_5c" in path.name
    ]
    assert stage_migrations == []
