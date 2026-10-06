import os

from .test_settings import *

# Explicit, isolated PostgreSQL target. Never inherit the application's DATABASE_URL.
# The filename intentionally avoids test*.py so SQLite test discovery won't import it.
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": "postgres",
    "HOST": os.environ["INOUT_TEST_PG_HOST"],
    "PORT": os.environ.get("INOUT_TEST_PG_PORT", "5432"),
    "USER": os.environ["INOUT_TEST_PG_USER"],
    "PASSWORD": os.environ.get("INOUT_TEST_PG_PASSWORD", ""),
    "TEST": {"NAME": "test_inout_migration"},
}}
