import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-development-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "engine",
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"


def database_from_url(url):
    parts = urlparse(url)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parts.path.lstrip("/"),
        "USER": parts.username,
        "PASSWORD": parts.password,
        "HOST": parts.hostname,
        "PORT": parts.port or 5432,
    }


DATABASES = {
    "default": database_from_url(
        os.environ.get("DATABASE_URL", "postgres://pipeline:pipeline@localhost:5432/pipeline")
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_TZ = True
TIME_ZONE = "UTC"

# Rulesets are registered at startup from these modules. Each module exposes a
# RULESET tuple of versions and a DEFAULT version.
RULESETS = [
    "rulesets.lending",
    "rulesets.metering",
]

BUREAU_BASE_URL = os.environ.get("BUREAU_BASE_URL", "http://localhost:8001")
BUREAU_TIMEOUT_SECONDS = float(os.environ.get("BUREAU_TIMEOUT_SECONDS", "2.0"))
