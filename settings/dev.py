from .base import *
from src.config import PRODUCTION_DB


SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key")
DEBUG = True

# Use SQLite by default for quick local setup, but allow overriding
# with Postgres environment variables (useful when running Postgres
# in Docker and running `python manage.py runserver` locally).
if os.getenv("DB_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "mstore_db"),
            "USER": os.getenv("DB_USER", "devuser"),
            "PASSWORD": os.getenv("DB_PASSWORD", "dev_password"),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "*"]

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
]

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


