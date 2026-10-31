"""Expose the system-wide appearance settings to every template."""

from .models import AppearanceSettings


def appearance(request):
    return {'appearance': AppearanceSettings.load()}
