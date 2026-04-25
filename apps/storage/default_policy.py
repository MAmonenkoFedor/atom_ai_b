"""Single active default storage provider; repair after CRUD."""

from __future__ import annotations

from apps.storage.models import StorageProvider


def repair_storage_provider_defaults() -> None:
    """Clear default on inactive rows; if no active default remains, promote the first active provider."""
    StorageProvider.objects.filter(is_active=False, is_default=True).update(is_default=False)

    active = StorageProvider.objects.filter(is_active=True).order_by("priority", "code")
    if not active.exists():
        return

    marked = list(active.filter(is_default=True))
    if len(marked) == 1:
        return
    if len(marked) > 1:
        keeper = marked[0]
        StorageProvider.objects.filter(is_default=True).exclude(pk=keeper.pk).update(is_default=False)
        return

    first = active.first()
    if first and not first.is_default:
        StorageProvider.objects.filter(pk=first.pk).update(is_default=True)
