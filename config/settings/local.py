from .base import *  # noqa

DEBUG = True

# Локально удобнее создавать тестовых пользователей из кабинета супер-админа без подбора «нераспространённого» пароля.
# В production/staging используйте полный набор из base.py (включая CommonPasswordValidator).
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# SPA (Vite) on another origin: cookies + CSRF for session auth
CORS_ALLOW_CREDENTIALS = True
# Vite may hop ports when the default is busy; keep a small local allowlist so CSRF checks pass.
_vite_dev = tuple(
    f"http://{host}:{port}"
    for host in ("localhost", "127.0.0.1")
    for port in range(5170, 5190)
)
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys([*_vite_dev]))
if CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS = list(dict.fromkeys([*CORS_ALLOWED_ORIGINS, *_vite_dev]))
else:
    CORS_ALLOWED_ORIGINS = list(_vite_dev)
