"""Policy helpers layered on top of access grants."""

from __future__ import annotations

from dataclasses import dataclass

from apps.access import resolver as access_resolver


@dataclass(frozen=True)
class AiWorkspaceAccessDecision:
    can_view_metadata: bool
    can_view_content: bool
    reason: str


def resolve_ai_workspace_access(*, viewer, owner_user_id: int) -> AiWorkspaceAccessDecision:
    if not viewer or not getattr(viewer, "is_authenticated", False):
        return AiWorkspaceAccessDecision(False, False, "anonymous")

    if int(getattr(viewer, "id", 0) or 0) == int(owner_user_id):
        return AiWorkspaceAccessDecision(True, True, "self")

    if bool(getattr(viewer, "is_superuser", False)):
        return AiWorkspaceAccessDecision(True, True, "superuser")

    scope_id = str(owner_user_id)
    can_view_content = access_resolver.has_permission(
        viewer,
        "ai.workspace.view_content",
        scope_type="ai_workspace",
        scope_id=scope_id,
    )
    if can_view_content:
        return AiWorkspaceAccessDecision(True, True, "permission:ai.workspace.view_content")

    can_view_metadata = access_resolver.has_permission(
        viewer,
        "ai.workspace.view_metadata",
        scope_type="ai_workspace",
        scope_id=scope_id,
    )
    if can_view_metadata:
        return AiWorkspaceAccessDecision(True, False, "permission:ai.workspace.view_metadata")

    return AiWorkspaceAccessDecision(False, False, "no_permission")
