# --- Arriba de todo ---
import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

# BASE_DIR
BASE_DIR = Path(__file__).resolve().parent.parent

# =======================
# 🔐 Seguridad
# =======================
SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
DEBUG = os.getenv("DEBUG", "0") == "1"

# ALLOWED_HOSTS (Render + local)
ALLOWED_HOSTS = []
render_url = os.getenv("RENDER_EXTERNAL_URL")
if render_url:
    host = urlparse(render_url).netloc
    ALLOWED_HOSTS += [host]
ALLOWED_HOSTS += os.getenv("ALLOWED_HOSTS", "").split(",") if os.getenv("ALLOWED_HOSTS") else []
if DEBUG:
    ALLOWED_HOSTS = ["*"]

# CSRF Trusted (Render)
CSRF_TRUSTED_ORIGINS = []
if render_url:
    CSRF_TRUSTED_ORIGINS.append(render_url)

# =======================
# 🌐 Aplicaciones instaladas
# =======================
INSTALLED_APPS = [
    # Apps base de Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",  # ✅ importante para collectstatic

    # Terceros
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "drf_spectacular",

    # Tus apps locales
    "core",
    "accounts",
    "access_ctrl",
]

# =======================
# ⚙️ Middleware
# =======================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # ✅ para servir static en Render
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",        # ✅ CORS
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# =======================
# 📂 URLs y WSGI
# =======================
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"


# =======================
# 🧱 Base de datos
# =======================
if os.getenv("DATABASE_URL"):
    import dj_database_url
    DATABASES = {"default": dj_database_url.parse(os.getenv("DATABASE_URL"), conn_max_age=600)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# =======================
# 🌍 Internacionalización
# =======================
LANGUAGE_CODE = "es"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

# =======================
# 🗂 Archivos estáticos y multimedia
# =======================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# =======================
# 🎨 Templates
# =======================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # opcional
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# =======================
# 🔑 DRF y JWT
# =======================
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# =======================
# 📘 drf-spectacular
# =======================
SPECTACULAR_SETTINGS = {
    "TITLE": "InOut Access API",
    "DESCRIPTION": "Backend para el sistema de control de acceso, desarrollado con Django REST Framework",
    "VERSION": "1.0.0",
}

# =======================
# 🌍 CORS
# =======================
CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL", "0") == "1"
CORS_ALLOWED_ORIGINS = (
    os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if os.getenv("CORS_ALLOWED_ORIGINS") else []
)

# =======================
# ⚙️ Config general
# =======================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

