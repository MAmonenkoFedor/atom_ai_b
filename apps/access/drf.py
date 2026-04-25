"""DRF permission that delegates the check to the access resolver.

Use this on views that should be guarded by a specific permission code
from ``apps.access.PermissionDefinition``.

Usage on a view::

    class MyView(APIView):
        permission_classes = [IsAuthenticated, HasAccessPermission]
        access_required = "project.assign_rights"
        access_scope_type = "project"            # optional, default: any
        access_scope_id_kwarg = "project_id"     # optional URL kwarg

The view may also implement ``resolve_access_scope(request, view) -> tuple[scope_type, scope_id]``
for dynamic scopes (e.g. derived from request data).
"""

from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission

from apps.access.resolver import has_permission as access_has_permission


class HasAccessPermission(BasePermission):
    message = "You do not have the required permission for this action."

    def has_permission(self, request, view) -> bool:  # type: ignore[override]
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        code: str | None = getattr(view, "access_required", None)
        if not code:
            return True

        scope_type: str | None = getattr(view, "access_scope_type", None)
        scope_id: Any = None

        resolver = getattr(view, "resolve_access_scope", None)
        if callable(resolver):
            try:
                resolved = resolver(request, view)
            except Exception:
                resolved = None
            if isinstance(resolved, tuple) and len(resolved) == 2:
                scope_type, scope_id = resolved

        if scope_id is None:
            kwarg = getattr(view, "access_scope_id_kwarg", None)
            if kwarg:
                scope_id = (view.kwargs or {}).get(kwarg)

        return access_has_permission(
            user=user,
            code=code,
            scope_type=scope_type,
            scope_id=scope_id,
        )
