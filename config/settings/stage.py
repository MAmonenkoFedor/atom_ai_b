from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa
from .base import SECRET_KEY

DEBUG = False

# Mirror the production guard: stage must also run on a real secret,
# not the dev fallback compiled into base.py.
if not SECRET_KEY or SECRET_KEY == "unsafe-dev-secret":
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a strong random value on stage."
    )
