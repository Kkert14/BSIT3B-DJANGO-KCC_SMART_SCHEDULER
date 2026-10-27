"""Expose the current user's role to every template.

Registered in ``settings.TEMPLATES['OPTIONS']['context_processors']``.
Templates use ``{% if can_manage %}`` to hide admin-only controls such as the
Add / Edit / Delete / Import / Export buttons.
"""

from .decorators import ROLE_ADMIN, get_user_role


def role_context(request):
    """Return template context with the user's role and manage permission."""
    user = getattr(request, 'user', None)
    role = get_user_role(user) if user is not None else None
    return {
        'user_role': role,
        'can_manage': role == ROLE_ADMIN,
    }
