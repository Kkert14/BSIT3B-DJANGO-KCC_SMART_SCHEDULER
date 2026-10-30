"""Template context processors exposing the active curriculum and semester."""

from .models import Curriculum


def active_curriculum_semester(request):
    """Inject active curriculum / semester into every template context."""
    curricula = list(
        Curriculum.objects.prefetch_related('semesters').all()
    )
    active_curriculum = next((cur for cur in curricula if cur.is_active), None)
    active_semesters = []
    active_semester = None
    if active_curriculum:
        active_semesters = list(active_curriculum.semesters.all())
        active_semester = next((sem for sem in active_semesters if sem.is_active), None)
    return {
        'curricula': curricula,
        'active_curriculum': active_curriculum,
        'active_semesters': active_semesters,
        'active_semester': active_semester,
    }
