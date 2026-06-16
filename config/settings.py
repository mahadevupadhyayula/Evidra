from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def database_from_url(url: str | None) -> dict[str, object]:
    if not url:
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}

    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must use postgres://, postgresql://, or be unset locally.")

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username or "",
        "PASSWORD": parsed.password or "",
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
    }


LOCAL_DEVELOPMENT_SECRET_KEY = "insecure-local-development-key"


def get_secret_key(*, debug: bool) -> str:
    secret_key = os.getenv("DJANGO_SECRET_KEY")
    if secret_key and secret_key != LOCAL_DEVELOPMENT_SECRET_KEY:
        return secret_key
    if debug:
        return LOCAL_DEVELOPMENT_SECRET_KEY
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false.")


DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = get_secret_key(debug=DEBUG)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.common",
    "apps.documents",
    "apps.profiles",
    "apps.opportunities",
    "apps.evidence",
    "apps.stories",
    "apps.matching",
    "apps.previews",
    "apps.payments",
    "apps.prepkits",
    "apps.practice",
    "apps.generations",
    "apps.sprints",
    "apps.workspace",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": database_from_url(os.getenv("DATABASE_URL"))}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
PRIVATE_MEDIA_ROOT = Path(
    os.getenv("EVIDRA_PRIVATE_STORAGE_ROOT", BASE_DIR / ".private" / "uploads")
)
RESUME_MAX_UPLOAD_BYTES = int(os.getenv("EVIDRA_RESUME_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
EVIDRA_OPENAI_MODEL = os.getenv("EVIDRA_OPENAI_MODEL", "gpt-4o-mini")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
INTERVIEW_SPRINT_PRICE_AMOUNT = int(
    os.getenv("INTERVIEW_SPRINT_PRICE_AMOUNT", "499900" if DEBUG else "0")
)
INTERVIEW_SPRINT_PRICE_CURRENCY = os.getenv("INTERVIEW_SPRINT_PRICE_CURRENCY", "INR")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "workspace:index"
LOGOUT_REDIRECT_URL = "home"
