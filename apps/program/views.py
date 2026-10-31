from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError

from .models import MAJOR_CHOICES, Program
from apps.curriculum.models import Curriculum, Semester
from apps.subject.models import Subject
from apps.users.decorators import admin_required_api


YEAR_LEVEL_LABELS = {
    1: '1st year',
    2: '2nd year',
    3: '3rd year',
    4: '4th year',
    5: '5th year',
    6: '6th year',
}

YEAR_LEVEL_CHOICES = [(level, YEAR_LEVEL_LABELS[level]) for level in range(1, 6)]


def program_list_context(request):
    """Context for the Programs page."""
    query = request.GET.get('q', '').strip()
    programs_list = Program.objects.all()
    if query:
        programs_list = programs_list.filter(
            Q(program_code__icontains=query)
            | Q(program_description__icontains=query)
            | Q(major__icontains=query)
            | Q(department__icontains=query)
        )
    paginator = Paginator(programs_list, 10)
    page_number = request.GET.get('page', 1)
    programs = paginator.get_page(page_number)
    return {
        'programs': programs,
        'query': query,
        'major_choices': MAJOR_CHOICES,
    }


@login_required(login_url='login')
def program_list_page(request):
    """Programs page: degrees with their course offerings behind each row."""
    return render(request, 'program_list.html', program_list_context(request))


@login_required(login_url='login')
def program_list_ajax(request):
    programs = program_list_context(request)['programs']
    data = list(programs.object_list.values(
        'id', 'program_code', 'program_description', 'major', 'department', 'is_active'
    ))
    return JsonResponse({
        'data': data,
        'has_next': programs.has_next(),
        'has_prev': programs.has_previous(),
        'page': programs.number,
        'pages': programs.paginator.num_pages,
        'total': programs.paginator.count,
    })


@login_required(login_url='login')
def program_get_ajax(request, pk):
    program = get_object_or_404(Program, pk=pk)
    return JsonResponse({
        'id': program.id,
        'program_code': program.program_code,
        'program_description': program.program_description,
        'major': program.major,
        'department': program.department,
        'is_active': program.is_active,
    })


@login_required(login_url='login')
def program_courses_page(request, pk):
    """One program's courses for an academic year, grouped by year level."""
    program = get_object_or_404(Program, pk=pk)

    subjects_qs = Subject.objects.filter(program=program).select_related(
        'semester__curriculum', 'prerequisite'
    )

    program_year_ids = list(
        subjects_qs.values_list('semester__curriculum_id', flat=True).distinct()
    )
    curriculum_ids = set(Curriculum.objects.values_list('id', flat=True))

    filter_year = request.GET.get('year', '').strip()
    if not filter_year.isdigit() or int(filter_year) not in curriculum_ids:
        # Prefer the active curriculum, then the newest one holding this
        # program's courses, then any curriculum, so the page opens populated.
        active_year_id = (
            Curriculum.objects.filter(is_active=True)
            .values_list('id', flat=True)
            .first()
        )
        if active_year_id in program_year_ids:
            filter_year = str(active_year_id)
        else:
            newest_year_id = (
                Curriculum.objects.filter(id__in=program_year_ids)
                .order_by('-academic_year')
                .values_list('id', flat=True)
                .first()
            )
            if newest_year_id:
                filter_year = str(newest_year_id)
            elif active_year_id:
                filter_year = str(active_year_id)
            else:
                newest_year_id = (
                    Curriculum.objects.order_by('-academic_year')
                    .values_list('id', flat=True)
                    .first()
                )
                filter_year = str(newest_year_id) if newest_year_id else ''

    selected_curriculum = (
        Curriculum.objects.filter(pk=int(filter_year)).first() if filter_year else None
    )
    subjects = []
    if selected_curriculum:
        subjects = list(
            subjects_qs.filter(semester__curriculum=selected_curriculum).order_by(
                'year_level', 'semester__semester_number', 'code'
            )
        )

    groups = []
    for level in sorted({subject.year_level for subject in subjects}):
        level_subjects = [subject for subject in subjects if subject.year_level == level]
        groups.append({
            'level': level,
            'label': YEAR_LEVEL_LABELS.get(level, f'{level}th year'),
            'subjects': level_subjects,
            'units': sum((subject.units for subject in level_subjects), 0),
            'lecture_hours': sum(subject.lecture_hours for subject in level_subjects),
            'lab_hours': sum(subject.lab_hours for subject in level_subjects),
            'total_hours': sum(subject.total_hours for subject in level_subjects),
        })

    context = {
        'program': program,
        'curricula': Curriculum.objects.order_by('-academic_year'),
        'selected_curriculum': selected_curriculum,
        'filter_year': filter_year,
        'groups': groups,
        'course_count': len(subjects),
        'total_units': sum((subject.units for subject in subjects), 0),
        'lecture_hours': sum(subject.lecture_hours for subject in subjects),
        'lab_hours': sum(subject.lab_hours for subject in subjects),
        'total_hours': sum(subject.total_hours for subject in subjects),
        'has_courses': subjects_qs.exists(),
        'semesters': (
            Semester.objects.filter(curriculum=selected_curriculum)
            .order_by('semester_number')
            if selected_curriculum else Semester.objects.none()
        ),
        'prerequisite_choices': Subject.objects.filter(program=program).order_by('code'),
        'year_level_choices': YEAR_LEVEL_CHOICES,
    }
    return render(request, 'program_courses.html', context)


@admin_required_api
@login_required(login_url='login')
@require_POST
def program_save_ajax(request):
    program_id = request.POST.get('id')
    if program_id:
        program = get_object_or_404(Program, pk=program_id)
    else:
        program = Program()

    program_code = request.POST.get('program_code', '').strip()
    program_description = request.POST.get('program_description', '').strip()
    major = request.POST.get('major', '').strip()
    department = request.POST.get('department', '').strip()
    is_active = request.POST.get('is_active') == 'true'

    if not program_code:
        return JsonResponse({'error': 'Program code is required.'}, status=400)
    if not program_description:
        return JsonResponse({'error': 'Program description is required.'}, status=400)

    dup_qs = Program.objects.filter(Q(program_code=program_code) | Q(program_description=program_description))
    if program_id:
        dup_qs = dup_qs.exclude(pk=program_id)
    if dup_qs.filter(program_code=program_code).exists():
        return JsonResponse({'error': 'That program code is already taken.'}, status=400)
    if dup_qs.filter(program_description=program_description).exists():
        return JsonResponse({'error': 'That program description is already in use.'}, status=400)

    program.program_code = program_code
    program.program_description = program_description
    program.major = major
    program.department = department
    program.is_active = is_active

    try:
        program.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save program due to a conflict.'}, status=400)

    messages.success(request, f'Program "{program.program_code}" has been saved successfully.')
    return JsonResponse({
        'status': 'success',
        'id': program.id,
        'program_code': program.program_code,
        'program_description': program.program_description,
        'major': program.major,
        'department': program.department,
        'is_active': program.is_active,
    })


@admin_required_api
@login_required(login_url='login')
@require_POST
def program_delete_ajax(request, pk):
    program = get_object_or_404(Program, pk=pk)
    program_code = program.program_code
    program.delete()
    messages.success(request, f'Program "{program_code}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})
