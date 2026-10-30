"""Role-based access control helpers for the Smart Scheduler apps.

Roles live on ``UserProfile.role`` and are one of ``admin``, ``teacher`` or
``student``. Superusers implicitly hold every role.

Two flavours of guard are provided:

``role_required``
    For page views. A user without the required role is redirected back to the
    dashboard with an explanatory message.

``api_role_required``
    For JSON endpoints (``*_ajax``). A user without the
    required role receives a JSON ``403`` instead of a redirect, so the
    front-end ``fetch()`` handlers can surface the error instead of choking on
    an HTML response.
"""

from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

from .models import UserProfile

ROLE_ADMIN = 'admin'
ROLE_TEACHER = 'teacher'
ROLE_STUDENT = 'student'

ROLE_CHOICES = (ROLE_ADMIN, ROLE_TEACHER, ROLE_STUDENT)


def get_user_role(user):
    """Return the role of ``user``.

    Returns ``None`` for anonymous users, ``'admin'`` for superusers, and
    falls back to ``'student'`` when a profile has not been created yet.
    """
    if not getattr(user, 'is_authenticated', False):
        return None
    if user.is_superuser:
        return ROLE_ADMIN
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        return ROLE_STUDENT
    return profile.role


def _denial_message(allowed_roles):
    return (
        'You do not have permission to perform this action. '
        'Required role: {}.'
    ).format(', '.join(allowed_roles))


def role_required(*allowed_roles):
    """Require the user to hold one of ``allowed_roles`` (page views).

    Usage:
        @role_required('admin')
        @role_required('admin', 'teacher')
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            # Superusers have access to everything.
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            if get_user_role(request.user) in allowed_roles:
                return view_func(request, *args, **kwargs)

            # Role not allowed - redirect with message.
            messages.error(request, _denial_message(allowed_roles))
            return redirect('dashboard')

        return _wrapped_view
    return decorator


def api_role_required(*allowed_roles):
    """Require the user to hold one of ``allowed_roles`` (JSON endpoints)."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse(
                    {'error': 'Authentication required.'}, status=401
                )

            # Superusers have access to everything.
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            if get_user_role(request.user) in allowed_roles:
                return view_func(request, *args, **kwargs)

            return JsonResponse(
                {'error': _denial_message(allowed_roles)}, status=403
            )

        return _wrapped_view
    return decorator


def admin_required(view_func):
    """Require admin role (page view)."""
    return role_required(ROLE_ADMIN)(view_func)


def admin_required_api(view_func):
    """Require admin role (JSON endpoint)."""
    return api_role_required(ROLE_ADMIN)(view_func)


def teacher_required(view_func):
    """Require teacher or admin role (page view)."""
    return role_required(ROLE_ADMIN, ROLE_TEACHER)(view_func)


def teacher_required_api(view_func):
    """Require teacher or admin role (JSON endpoint)."""
    return api_role_required(ROLE_ADMIN, ROLE_TEACHER)(view_func)


def student_required(view_func):
    """Require student role (page view)."""
    return role_required(ROLE_STUDENT)(view_func)


def is_admin(user):
    """Check if user has admin role."""
    return get_user_role(user) == ROLE_ADMIN


def is_teacher(user):
    """Check if user has teacher or admin role."""
    return get_user_role(user) in (ROLE_ADMIN, ROLE_TEACHER)


def is_student(user):
    """Check if user has student role (superusers are not students)."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return False
    return get_user_role(user) == ROLE_STUDENT
