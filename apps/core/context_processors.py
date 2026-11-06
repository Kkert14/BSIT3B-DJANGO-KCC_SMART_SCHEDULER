"""Expose the system-wide appearance settings to every template."""

import os

from django.conf import settings

from .models import AppearanceSettings


def appearance(request):
    return {'appearance': AppearanceSettings.load()}


def static_version(request):
    """mtime-based version for shell.css so style changes bust the browser cache."""
    try:
        mtime = os.path.getmtime(os.path.join(settings.BASE_DIR, 'static', 'css', 'shell.css'))
    except OSError:
        mtime = 0
    return {'shell_css_version': int(mtime)}
