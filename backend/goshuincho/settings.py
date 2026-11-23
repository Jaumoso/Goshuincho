import os
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise ImproperlyConfigured(f"Falta la variable de entorno {name}")
    return value


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


DEBUG = env_bool("DEBUG")
SECRET_KEY = env("SECRET_KEY", required=True)
VERSION = env("GOSHUINCHO_VERSION", "dev")

PUBLIC_URL = env("PUBLIC_URL", "http://localhost:8000").rstrip("/")
_public = urlsplit(PUBLIC_URL)
if _public.scheme not in {"http", "https"} or not _public.hostname:
    raise ImproperlyConfigured("PUBLIC_URL debe ser una URL http(s) completa")

ALLOWED_HOSTS = [_public.hostname, "localhost", "127.0.0.1", *env_list("EXTRA_ALLOWED_HOSTS")]
CSRF_TRUSTED_ORIGINS = [f"{_public.scheme}://{_public.netloc}"]

# Cabeceras X-Forwarded-* aceptadas solo si la petición llega desde estas redes
# (ver goshuincho.middleware.TrustedProxyMiddleware).
TRUSTED_PROXIES = env_list("TRUSTED_PROXIES", "127.0.0.1,::1")

_https = _public.scheme == "https"
SESSION_COOKIE_SECURE = _https
CSRF_COOKIE_SECURE = _https
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "axes",
    "procrastinate.contrib.django",
    "accounts",
    "geo",
]

MIDDLEWARE = [
    "goshuincho.middleware.TrustedProxyMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "goshuincho.urls"
WSGI_APPLICATION = "goshuincho.wsgi.application"

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

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "HOST": env("DB_HOST", "db"),
        "PORT": env("DB_PORT", "5432"),
        "NAME": env("DB_NAME", "goshuin"),
        "USER": env("DB_USER", "goshuin"),
        "PASSWORD": env("DB_PASSWORD", ""),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.25  # horas
AXES_LOCKOUT_PARAMETERS = [["ip_address", "username"]]
AXES_RESET_ON_SUCCESS = True
AXES_USERNAME_CALLABLE = "accounts.axes.axes_username"

LANGUAGE_CODE = "es"
LANGUAGES = [("es", "Español"), ("en", "English")]
TIME_ZONE = "Asia/Tokyo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = Path(env("STATIC_ROOT", BASE_DIR / "staticfiles"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Build de la PWA: WhiteNoise sirve sus ficheros en la raíz y la vista spa() devuelve index.html.
FRONTEND_DIST = Path(env("FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.is_dir() else None
WHITENOISE_INDEX_FILE = False


def WHITENOISE_IMMUTABLE_FILE_TEST(path, url):
    return url.startswith("/assets/") or url.startswith(STATIC_URL)


MEDIA_ROOT = Path(env("MEDIA_ROOT", "/data/media"))
MAX_UPLOAD_MB = int(env("MAX_UPLOAD_MB", "25"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
KEEP_ORIGINAL_EXIF = env_bool("KEEP_ORIGINAL_EXIF", True)

ADMIN_EMAIL = env("ADMIN_EMAIL")
ADMIN_PASSWORD = env("ADMIN_PASSWORD")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {"axes": {"level": "WARNING"}},
}
