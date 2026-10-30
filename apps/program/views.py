from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError
from django.template.loader import render_to_string

from .models import MAJOR_CHOICES, Program
from apps.curriculum.models import Curriculum, Semester
from apps.curriculum.views import curriculum_list_context
from apps.subject.models import Subject
from apps.subject.views import subject_list_context
from apps.users.decorators import admin_required, admin_required_api, is_admin


PROGRAM_TABS = ('programs', 'curriculum', 'courses')

YEAR_LEVEL_LABELS = {
    1: '1st year',
    2: '2nd year',
    3: '3rd year',
    4: '4th year',
    5: '5th year',
    6: '6th year',
}

SEMESTER_NUMBERS = {'1', '2', '3'}


def program_list_context(request):
    """Context for the Programs tab of the Programs hub."""
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
    """Programs hub: Programs, Curriculum and Courses in one page."""
    tab = request.GET.get('tab', 'programs')
    if tab not in PROGRAM_TABS:
        tab = 'programs'

    if tab == 'curriculum' and not is_admin(request.user):
        messages.error(
            request,
            'You do not have permission to perform this action. Required role: admin.',
        )
        return redirect('dashboard')

    if tab == 'curriculum':
        context = curriculum_list_context(request)
    elif tab == 'courses':
        context = subject_list_context(request)
    else:
        context = program_list_context(request)

    context['active_tab'] = tab
    return render(request, 'program_list.html', context)


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
def program_courses_ajax(request, pk):
    """Curriculum view for one program, filtered by A.Y., semester and year level."""
    program = get_object_or_404(Program, pk=pk)

    subjects_qs = Subject.objects.filter(program=program).select_related(
        'semester__curriculum', 'prerequisite'
    )

    year_param = request.GET.get('year')
    if year_param is None:
        # Prefer the active curriculum, then the newest one holding this
        # program's courses, so the modal opens on a populated curriculum.
        program_year_ids = list(
            subjects_qs.values_list('semester__curriculum_id', flat=True).distinct()
        )
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
            filter_year = str(newest_year_id) if newest_year_id else ''
    else:
        filter_year = year_param.strip()
    if filter_year and not filter_year.isdigit():
        filter_year = ''

    filter_semester = request.GET.get('semester', '').strip()
    if filter_semester not in SEMESTER_NUMBERS:
        filter_semester = ''

    filter_year_level = request.GET.get('year_level', '').strip()
    if filter_year_level and not filter_year_level.isdigit():
        filter_year_level = ''

    scoped_qs = subjects_qs
    if filter_year:
        scoped_qs = scoped_qs.filter(semester__curriculum_id=filter_year)
    if filter_semester:
        scoped_qs = scoped_qs.filter(semester__semester_number=filter_semester)

    year_level_values = list(
        scoped_qs.values_list('year_level', flat=True).distinct().order_by('year_level')
    )
    if filter_year_level and filter_year_level not in {str(level) for level in year_level_values}:
        filter_year_level = ''
    if filter_year_level:
        scoped_qs = scoped_qs.filter(year_level=filter_year_level)

    subjects = list(scoped_qs.order_by(
        'year_level', 'semester__semester_number', 'code'
    ))

    groups = []
    for level in year_level_values:
        level_subjects = [subject for subject in subjects if subject.year_level == level]
        if not level_subjects:
            continue
        groups.append({
            'label': YEAR_LEVEL_LABELS.get(level, f'{level}th year'),
            'subjects': level_subjects,
            'units': sum((subject.units for subject in level_subjects), 0),
        })

    context = {
        'program': program,
        'curricula': Curriculum.objects.order_by('-academic_year'),
        'semester_choices': Semester.SEMESTER_CHOICES,
        'year_level_choices': [
            (level, YEAR_LEVEL_LABELS.get(level, f'{level}th year'))
            for level in year_level_values
        ],
        'filter_year': filter_year,
        'filter_semester': filter_semester,
        'filter_year_level': filter_year_level,
        'groups': groups,
        'course_count': len(subjects),
        'total_units': sum((subject.units for subject in subjects), 0),
        'has_courses': subjects_qs.exists(),
    }
    html = render_to_string(
        'partials/program_courses_content.html', context, request=request
    )
    return JsonResponse({'html': html, 'count': len(subjects)})


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
