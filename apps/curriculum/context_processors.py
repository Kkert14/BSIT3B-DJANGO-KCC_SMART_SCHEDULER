"""Template context processors exposing the active curriculum and semester."""

from .models import Curriculum, Semester


def active_curriculum_semester(request):
    """Inject active curriculum / semester into every template context."""
    curricula = (
        Curriculum.objects.select_related('program')
        .prefetch_related('semesters')
        .all()
    )
    active_curriculum = curricula.filter(is_active=True).first()
    active_semester = None
    if active_curriculum:
        active_semester = Semester.objects.filter(
            curriculum=active_curriculum,
            is_active=True,
        ).first()
    return {
        'curricula': curricula,
        'active_curriculum': active_curriculum,
        'active_semester': active_semester,
    }
