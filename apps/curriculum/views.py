import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import IntegrityError

from apps.core.models import ACCENT_PRESETS, FONT_STACKS, AppearanceSettings
from apps.users.decorators import admin_required, admin_required_api

from .models import ACADEMIC_YEAR_CHOICES, Curriculum, Semester


def curriculum_list_context(request):
    """Context for the curriculum and appearance sections of Settings."""
    query = request.GET.get('q', '').strip()
    curricula = Curriculum.objects.prefetch_related('semesters').all()
    if query:
        curricula = curricula.filter(academic_year__icontains=query)
    paginator = Paginator(curricula, 10)
    page_number = request.GET.get('page', 1)
    curricula = paginator.get_page(page_number)
    return {
        'curricula': curricula,
        'query': query,
        'academic_year_choices': ACADEMIC_YEAR_CHOICES,
        'existing_academic_years': list(
            Curriculum.objects.values_list('academic_year', flat=True)
        ),
        'accent_presets': ACCENT_PRESETS,
        'font_options': [
            {'value': value, 'label': label, 'stack': FONT_STACKS[value]}
            for value, label in AppearanceSettings.FONT_CHOICES
        ],
    }


@login_required(login_url='login')
@admin_required
def curriculum_list(request):
    """Settings page holding the curriculum and semester management."""
    return render(request, 'settings.html', curriculum_list_context(request))


@login_required(login_url='login')
@admin_required_api
@require_POST
def curriculum_save_ajax(request):
    curriculum_id = request.POST.get('id')
    if curriculum_id:
        curriculum = get_object_or_404(Curriculum, pk=curriculum_id)
    else:
        curriculum = Curriculum()

    academic_year = request.POST.get('academic_year', '').strip()
    is_active = request.POST.get('is_active') == 'true'

    if not academic_year:
        return JsonResponse({'error': 'Curriculum year is required.'}, status=400)

    if not re.match(r'^[0-9]{4}-[0-9]{4}$', academic_year):
        return JsonResponse({'error': 'Curriculum year must be in YYYY-YYYY format.'}, status=400)

    dup_qs = Curriculum.objects.filter(academic_year=academic_year)
    if curriculum_id:
        dup_qs = dup_qs.exclude(pk=curriculum_id)
    if dup_qs.exists():
        return JsonResponse(
            {'error': f'A.Y. {academic_year} already has a curriculum.'},
            status=400,
        )

    curriculum.academic_year = academic_year
    curriculum.is_active = is_active

    try:
        curriculum.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save curriculum due to a conflict.'}, status=400)

    created_semesters = []
    if not curriculum_id:
        for raw_number in request.POST.getlist('semester_numbers'):
            if raw_number not in ('1', '2', '3'):
                continue
            semester, _ = Semester.objects.get_or_create(
                curriculum=curriculum,
                semester_number=int(raw_number),
            )
            created_semesters.append(semester)
        if curriculum.is_active and created_semesters:
            first = created_semesters[0]
            first.is_active = True
            first.save()

    message = f'A.Y. {curriculum.academic_year} curriculum has been saved successfully.'
    if created_semesters:
        labels = ', '.join(s.get_semester_number_display() for s in created_semesters)
        message = f'A.Y. {curriculum.academic_year} curriculum has been saved with {labels}.'
    messages.success(request, message)
    return JsonResponse({
        'status': 'success',
        'id': curriculum.id,
        'academic_year': curriculum.academic_year,
        'is_active': curriculum.is_active,
    })


@login_required(login_url='login')
@admin_required_api
@require_POST
def curriculum_delete_ajax(request, pk):
    curriculum = get_object_or_404(Curriculum, pk=pk)
    if curriculum.semesters.exists():
        return JsonResponse(
            {'error': 'Cannot delete curriculum with existing semesters. Remove semesters first.'},
            status=400,
        )
    academic_year = curriculum.academic_year
    curriculum.delete()
    messages.success(
        request,
        f'A.Y. {academic_year} curriculum has been deleted successfully.',
    )
    return JsonResponse({'status': 'deleted'})


@login_required(login_url='login')
@admin_required_api
@require_POST
def semester_save_ajax(request):
    semester_id = request.POST.get('id')
    if semester_id:
        semester = get_object_or_404(Semester, pk=semester_id)
    else:
        semester = Semester()

    curriculum_id = request.POST.get('curriculum', '').strip()
    semester_number = request.POST.get('semester_number', '').strip()
    is_active = request.POST.get('is_active') == 'true'

    if not curriculum_id:
        return JsonResponse({'error': 'Curriculum is required.'}, status=400)
    if not semester_number:
        return JsonResponse({'error': 'Semester number is required.'}, status=400)

    try:
        semester_number = int(semester_number)
    except ValueError:
        return JsonResponse({'error': 'Semester number must be a number.'}, status=400)

    if semester_number not in (1, 2, 3):
        return JsonResponse({'error': 'Semester must be 1, 2 or Summer.'}, status=400)

    semester_label = dict(Semester.SEMESTER_CHOICES)[semester_number]

    try:
        curriculum = Curriculum.objects.get(pk=int(curriculum_id))
    except (Curriculum.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid curriculum.'}, status=400)

    dup_qs = Semester.objects.filter(curriculum=curriculum, semester_number=semester_number)
    if semester_id:
        dup_qs = dup_qs.exclude(pk=semester_id)
    if dup_qs.exists():
        return JsonResponse(
            {'error': f'{semester_label} already exists for this curriculum.'},
            status=400,
        )

    semester.curriculum = curriculum
    semester.semester_number = semester_number
    semester.is_active = is_active

    try:
        semester.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save semester due to a conflict.'}, status=400)

    messages.success(
        request,
        f'{semester_label} for A.Y. {curriculum.academic_year} has been saved successfully.',
    )
    return JsonResponse({
        'status': 'success',
        'id': semester.id,
        'curriculum': curriculum.id,
        'academic_year': curriculum.academic_year,
        'semester_number': semester.semester_number,
        'is_active': semester.is_active,
    })


@login_required(login_url='login')
@admin_required_api
@require_POST
def semester_delete_ajax(request, pk):
    semester = get_object_or_404(Semester, pk=pk)

    if semester.subjects.exists():
        return JsonResponse(
            {'error': 'Cannot delete semester with existing subjects. Remove subjects first.'},
            status=400,
        )
    if semester.sections.exists():
        return JsonResponse(
            {'error': 'Cannot delete semester with existing sections. Remove sections first.'},
            status=400,
        )
    if semester.schedules.exists():
        return JsonResponse(
            {'error': 'Cannot delete semester with existing schedules. Remove schedules first.'},
            status=400,
        )

    academic_year = semester.curriculum.academic_year
    semester_label = semester.get_semester_number_display()
    semester.delete()
    messages.success(
        request,
        f'{semester_label} for A.Y. {academic_year} has been deleted successfully.',
    )
    return JsonResponse({'status': 'deleted'})


@login_required(login_url='login')
@admin_required_api
@require_POST
def appearance_save_ajax(request):
    theme = request.POST.get('theme', '').strip()
    accent = request.POST.get('accent', '').strip().lower()
    font = request.POST.get('font', '').strip()

    if theme not in dict(AppearanceSettings.THEME_CHOICES):
        return JsonResponse({'error': 'Choose a valid theme.'}, status=400)
    if font not in FONT_STACKS:
        return JsonResponse({'error': 'Choose a valid font.'}, status=400)
    if not re.match(r'^#[0-9a-f]{6}$', accent):
        return JsonResponse({'error': 'Choose an accent colour in #rrggbb format.'}, status=400)

    appearance = AppearanceSettings.objects.first()
    if appearance is None:
        appearance = AppearanceSettings(pk=1)
    appearance.theme = theme
    appearance.accent = accent
    appearance.font = font
    appearance.save()

    messages.success(request, 'Appearance settings have been saved.')
    return JsonResponse({
        'status': 'success',
        'theme': appearance.theme,
        'accent': appearance.accent,
        'accent_rgb': appearance.accent_rgb,
        'font': appearance.font,
        'font_stack': appearance.font_stack,
    })


@login_required(login_url='login')
@admin_required
def set_active_curriculum(request, curriculum_id):
    curriculum = get_object_or_404(Curriculum, pk=curriculum_id)

    curriculum.is_active = True
    curriculum.save()

    semester = (
        curriculum.semesters.filter(is_active=True).first()
        or curriculum.semesters.order_by('semester_number').first()
    )
    if semester:
        semester.is_active = True
        semester.save()
        messages.success(
            request,
            f'Active curriculum year set to A.Y. {curriculum.academic_year} — '
            f'{semester.get_semester_number_display()}.',
        )
    else:
        messages.warning(
            request,
            f'A.Y. {curriculum.academic_year} has no semesters yet.',
        )
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


@login_required(login_url='login')
@admin_required
def set_active_semester(request, semester_id):
    semester = get_object_or_404(
        Semester.objects.select_related('curriculum'),
        pk=semester_id,
    )

    semester.is_active = True
    semester.save()
    semester.curriculum.is_active = True
    semester.curriculum.save()

    messages.success(
        request,
        f'Active curriculum set to A.Y. {semester.curriculum.academic_year} — '
        f'{semester.get_semester_number_display()}.',
    )
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))
