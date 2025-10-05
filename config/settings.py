# --- Arriba de todo ---
import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Seguridad (usar variables de entorno)
SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
DEBUG = os.getenv("DEBUG", "0") == "1"

# ALLOWED_HOSTS para Render y local
ALLOWED_HOSTS = []
render_url = os.getenv("RENDER_EXTERNAL_URL")
if render_url:
    host = urlparse(render_url).netloc
    ALLOWED_HOSTS += [host]
ALLOWED_HOSTS += os.getenv("ALLOWED_HOSTS", "").split(",") if os.getenv("ALLOWED_HOSTS") else []

# CSRF Trusted (Render)
CSRF_TRUSTED_ORIGINS = []
if render_url:
    CSRF_TRUSTED_ORIGINS.append(render_url)

# CORS (flexible por entorno)
CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL", "0") == "1"
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if os.getenv("CORS_ALLOWED_ORIGINS") else []

# Base de datos (Render → DATABASE_URL; local → sqlite)
if os.getenv("DATABASE_URL"):
    import dj_database_url
    DATABASES = {"default": dj_database_url.parse(os.getenv("DATABASE_URL"), conn_max_age=600)}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

# Zona horaria / locale
LANGUAGE_CODE = "es"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

# Staticfiles con WhiteNoise (NO duplicar)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# DRF / JWT (tu config actual)
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {"TITLE": "InOut Access API", "VERSION": "0.1.0"}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
