"""`access_control` — unified permission service.

This app is the single source of truth for *who is allowed to do what and in
which scope*. Other apps (projects, workspaces, orgstructure, ai, …) must
never invent permission checks of their own — they call
:func:`apps.access.resolver.has_permission` or
:func:`apps.access.resolver.can_delegate`.

Core rule (v1):

    **A permission exists only when there is an active grant in a concrete
    scope, issued by an allowed source and not revoked / not expired.**
"""

default_app_config = "apps.access.apps.AccessConfig"
