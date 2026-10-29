"""Minimal Django settings: no database, no sessions, no auth - persistence is
handled by the JSON file store in ``db/`` (see storage.py)."""
SECRET_KEY = "factwise-planner-dev-key"
DEBUG = True
ALLOWED_HOSTS = ["*"]
ROOT_URLCONF = "planner.urls"
INSTALLED_APPS = []
MIDDLEWARE = []
DATABASES = {}
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
