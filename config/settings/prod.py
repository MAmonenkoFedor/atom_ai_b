from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa
from .base import SECRET_KEY, env

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# Hard fail in production if DJANGO_SECRET_KEY is missing or left at the
# dev default. This prevents the well-known fallback secret in base.py
# from accidentally reaching production.
if not SECRET_KEY or SECRET_KEY == "unsafe-dev-secret":
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a strong random value in production."
    )
