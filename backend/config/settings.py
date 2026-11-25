"""
Django settings for the Property Onboarding platform.

All environment-specific values come from environment variables (or a .env file
in the backend folder). See .env.example.
"""
from pathlib import Path
import os

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [v.strip() for v in os.getenv(name, default).split(",") if v.strip()]


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "properties",
    "onboarding",
    "procurement",
    "agents",
    "listings",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
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
        "DIRS": [],
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

DATABASES = {
    "default": dj_database_url.config(
        default=os.getenv(
            "DATABASE_URL", "postgres://postgres:postgres@localhost:5432/onboarding"
        ),
        conn_max_age=60,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-ca"
TIME_ZONE = "America/Toronto"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- API ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": None,
}

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)

# --- Business settings ---
ONBOARDING = {
    # Listing nickname: A<sequence>-<CITY>-<STREET 3 letters><UNIT>, e.g. A37313-TOR-BAY617
    "NICKNAME_START": int(os.getenv("NICKNAME_START", "37331")),
    "DEFAULT_CITY_CODE": os.getenv("DEFAULT_CITY_CODE", "TOR"),
    "LICENCE_REMINDER_DAYS": [60, 30, 7],
}

PROCUREMENT = {
    # Flag an item when the current price is more than this fraction above its typical price.
    "OVER_PRICE_THRESHOLD": float(os.getenv("OVER_PRICE_THRESHOLD", "0.25")),
    # "web" reads each product link's page; "simulated" gives repeatable fake results for demos/tests.
    "PRICE_CHECKER": os.getenv("PRICE_CHECKER", "web"),
}

MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024

# --- Phase 2: agents and integrations ---
# Anything left blank runs in dry-run mode: the agent records what it *would* do.
INTEGRATIONS = {
    "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", ""),
    "ANTHROPIC_MODEL": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
    # Google service account JSON (with domain-wide delegation for Gmail and Admin SDK)
    "GOOGLE_SERVICE_ACCOUNT_FILE": os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", ""),
    "GOOGLE_DELEGATED_ADMIN": os.getenv("GOOGLE_DELEGATED_ADMIN", ""),     # Workspace admin to act as (Admin SDK)
    "GOOGLE_SENDER_EMAIL": os.getenv("GOOGLE_SENDER_EMAIL", ""),           # mailbox that sends approved emails
    "GOOGLE_DRIVE_PARENT_FOLDER_ID": os.getenv("GOOGLE_DRIVE_PARENT_FOLDER_ID", ""),
    "GOOGLE_TRACKER_SHEET_ID": os.getenv("GOOGLE_TRACKER_SHEET_ID", ""),
    "GOOGLE_TRACKER_RANGE": os.getenv("GOOGLE_TRACKER_RANGE", "Portfolio!A:J"),
}

AGENTS = {
    "UNIT_EMAIL_DOMAIN": os.getenv("UNIT_EMAIL_DOMAIN", "stays.example.com"),
    # Placeholders: {street} = 3-letter street code, {unit} = unit digits, {nickname} = full nickname
    "UNIT_EMAIL_PATTERN": os.getenv("UNIT_EMAIL_PATTERN", "{street}{unit}"),
    "OPS_EMAIL": os.getenv("OPS_EMAIL", "ops@stays.example.com"),
    "FOLLOWUP_DAYS": int(os.getenv("FOLLOWUP_DAYS", "5")),
    "DRIVE_SUBFOLDERS": ["Agreement", "Building registration", "Licence", "Inspection", "Orders", "Photos"],
    "LICENCE_REMINDER_DAYS": [60, 30, 7],
    # Default licence packet. CONFIRM WITH THE CLIENT: the exact City of Toronto requirements
    # and who provides each item. (key, label, source)
    "LICENCE_PACKET": [
        ("agreement", "Signed management agreement", "system"),
        ("unit_email", "Unique email address for the licence and listing", "system"),
        ("owner_consent", "Owner's written consent to short-term rental of the unit", "owner"),
        ("building_consent", "Building or condo confirmation that short-term rental is permitted", "building"),
        ("insurance", "Insurance certificate covering short-term rental", "owner"),
    ],
}

# --- Phase 3: listings ---
LISTINGS = {
    "GUESTY_CLIENT_ID": os.getenv("GUESTY_CLIENT_ID", ""),
    "GUESTY_CLIENT_SECRET": os.getenv("GUESTY_CLIENT_SECRET", ""),
    "GUESTY_BASE_URL": os.getenv("GUESTY_BASE_URL", "https://open-api.guesty.com"),
    # Guesty imports photos from URLs, so they must be reachable from the internet:
    # the backend's public address (e.g. https://onboarding-api.onrender.com). Not localhost.
    "PUBLIC_BASE_URL": os.getenv("PUBLIC_BASE_URL", ""),
    "ANGEL_HOST_EMAIL": os.getenv("ANGEL_HOST_EMAIL", ""),
    "MIN_PHOTOS": int(os.getenv("LISTING_MIN_PHOTOS", "5")),
    "DEFAULT_BASE_PRICE": int(os.getenv("LISTING_DEFAULT_BASE_PRICE", "150")),
    "CURRENCY": "CAD",
    "TIMEZONE": "America/Toronto",
}
