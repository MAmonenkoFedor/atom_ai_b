"""Stamp each HTTP request with a stable correlation id.

The middleware honors a client-provided ``X-Request-Id`` (or ``X-Trace-Id``)
header if present and looks safe; otherwise it generates a fresh UUID-4. The
id is exposed via:

* ``request.request_id`` and ``request.META["HTTP_X_REQUEST_ID"]`` for views,
* the response header ``X-Request-Id`` so the frontend can echo it in error
  reports / Sentry breadcrumbs.

The access service and audit service already read the id from request
headers, so installing this middleware is enough to get end-to-end tracing.
"""

from __future__ import annotations

import re
import uuid

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._\-]{6,128}$")
_HEADER = "X-Request-Id"
_META_KEYS = ("HTTP_X_REQUEST_ID", "HTTP_X_TRACE_ID")


def _client_provided_id(meta) -> str:
    for key in _META_KEYS:
        raw = (meta.get(key) or "").strip()
        if raw and _SAFE_ID_RE.match(raw):
            return raw[:128]
    return ""


class RequestIdMiddleware:
    """Generates / propagates ``X-Request-Id`` for every request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = _client_provided_id(request.META) or uuid.uuid4().hex
        request.request_id = rid
        request.META["HTTP_X_REQUEST_ID"] = rid

        response = self.get_response(request)
        response.headers[_HEADER] = rid
        return response
