import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from django.urls import get_resolver  # noqa: E402
from django.urls.resolvers import URLResolver  # noqa: E402


def walk(res, prefix=""):
    for p in res.url_patterns:
        base = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            walk(p, base)
        else:
            print(base)


walk(get_resolver())
