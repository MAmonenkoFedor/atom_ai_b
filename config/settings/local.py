from .base import *  # noqa

DEBUG = True

# SPA (Vite) on another origin: cookies + CSRF for session auth
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
_vite_dev = ("http://localhost:5173", "http://127.0.0.1:5173")
if CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS = list(dict.fromkeys([*CORS_ALLOWED_ORIGINS, *_vite_dev]))
else:
    CORS_ALLOWED_ORIGINS = list(_vite_dev)
