from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.users.decorators import admin_required

from .models import Curriculum, Semester


@login_required(login_url='login')
@admin_required
def curriculum_list(request):
    curricula = (
        Curriculum.objects.select_related('program')
        .prefetch_related('semesters')
        .all()
    )
    return render(request, 'curriculum_list.html', {'curricula': curricula})


@login_required(login_url='login')
@admin_required
def set_active_semester(request, semester_id):
    semester = get_object_or_404(
        Semester.objects.select_related('curriculum'),
        pk=semester_id,
    )

    # Activate this semester (deactivates other semesters in the same
    # curriculum via the model save override) and its curriculum
    # (deactivates all other curricula via the model save override).
    semester.is_active = True
    semester.save()
    semester.curriculum.is_active = True
    semester.curriculum.save()

    messages.success(
        request,
        f'Active curriculum set to {semester.curriculum.code} — '
        f'Semester {semester.semester_number}.',
    )
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))
