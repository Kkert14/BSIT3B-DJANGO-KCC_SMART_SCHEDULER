from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError

from apps.curriculum.models import Semester
from apps.program.models import Program
from .models import Section
from apps.users.decorators import admin_required, admin_required_api


@login_required(login_url='login')
def section_list_page(request):
    query = request.GET.get('q', '').strip()
    sections_list = Section.objects.select_related('program', 'semester__curriculum').all()
    if query:
        sections_list = sections_list.filter(
            Q(name__icontains=query) |
            Q(program__program_code__icontains=query) |
            Q(program__program_description__icontains=query) |
            Q(semester__curriculum__academic_year__icontains=query)
        )
    paginator = Paginator(sections_list, 10)
    page_number = request.GET.get('page', 1)
    sections = paginator.get_page(page_number)
    programs = Program.objects.filter(is_active=True).order_by('program_code')
    semesters = Semester.objects.select_related('curriculum').all().order_by('curriculum__academic_year', 'semester_number')
    return render(request, 'section_list.html', {
        'sections': sections,
        'query': query,
        'programs': programs,
        'semesters': semesters,
    })


@login_required(login_url='login')
def section_list_ajax(request):
    query = request.GET.get('q', '').strip()
    sections_list = Section.objects.select_related('program', 'semester__curriculum').all()
    if query:
        sections_list = sections_list.filter(
            Q(name__icontains=query) |
            Q(program__program_code__icontains=query) |
            Q(program__program_description__icontains=query) |
            Q(semester__curriculum__academic_year__icontains=query)
        )
    paginator = Paginator(sections_list, 10)
    page_number = request.GET.get('page', 1)
    sections = paginator.get_page(page_number)
    data = list(sections.object_list.values(
        'id', 'name', 'year_level', 'semester_id', 'capacity', 'is_active', 'program_id',
    ))
    for item in data:
        program = Program.objects.filter(pk=item.pop('program_id')).first()
        item['program'] = str(program) if program else ''
        semester = Semester.objects.filter(pk=item.pop('semester_id')).first()
        item['semester'] = str(semester) if semester else ''
        item['semester_number'] = semester.semester_number if semester else None
        item['academic_year'] = semester.curriculum.academic_year if semester else ''
    return JsonResponse({
        'data': data,
        'has_next': sections.has_next(),
        'has_prev': sections.has_previous(),
        'page': sections.number,
        'pages': sections.paginator.num_pages,
        'total': sections.paginator.count,
    })


@login_required(login_url='login')
def section_get_ajax(request, pk):
    section = get_object_or_404(Section.objects.select_related('program', 'semester__curriculum'), pk=pk)
    return JsonResponse({
        'id': section.id,
        'program': section.program.id,
        'program_name': str(section.program),
        'name': section.name,
        'year_level': section.year_level,
        'semester': section.semester.id,
        'semester_number': section.semester.semester_number,
        'academic_year': section.semester.curriculum.academic_year,
        'capacity': section.capacity,
        'is_active': section.is_active,
    })


@admin_required_api
@login_required(login_url='login')
@require_POST
def section_save_ajax(request):
    section_id = request.POST.get('id')
    if section_id:
        section = get_object_or_404(Section, pk=section_id)
    else:
        section = Section()

    program_id = request.POST.get('program')
    name = request.POST.get('name', '').strip()
    year_level = request.POST.get('year_level', '').strip()
    semester_id = request.POST.get('semester', '').strip()
    capacity = request.POST.get('capacity', '').strip()
    is_active = request.POST.get('is_active') == 'true'

    if not program_id:
        return JsonResponse({'error': 'Program is required.'}, status=400)
    try:
        program = Program.objects.get(pk=int(program_id))
    except (Program.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid program.'}, status=400)

    if not name:
        return JsonResponse({'error': 'Section name is required.'}, status=400)
    if not year_level:
        return JsonResponse({'error': 'Year level is required.'}, status=400)
    try:
        year_level = int(year_level)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Year level must be a number.'}, status=400)
    if not semester_id:
        return JsonResponse({'error': 'Semester is required.'}, status=400)
    try:
        semester = Semester.objects.get(pk=int(semester_id))
    except (Semester.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid semester.'}, status=400)
    if not capacity:
        return JsonResponse({'error': 'Capacity is required.'}, status=400)
    try:
        capacity = int(capacity)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Capacity must be a number.'}, status=400)

    dup_qs = Section.objects.filter(
        semester=semester, program=program, year_level=year_level, name=name
    )
    if section_id:
        dup_qs = dup_qs.exclude(pk=section_id)
    if dup_qs.exists():
        return JsonResponse({'error': 'A section with this identity already exists.'}, status=400)

    section.program = program
    section.name = name
    section.year_level = year_level
    section.semester = semester
    section.capacity = capacity
    section.is_active = is_active

    try:
        section.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save section due to a conflict.'}, status=400)

    messages.success(request, f'Section "{section.name}" has been saved successfully.')
    return JsonResponse({
        'status': 'success',
        'id': section.id,
        'program': section.program.id,
        'program_name': str(section.program),
        'name': section.name,
        'year_level': section.year_level,
        'semester': section.semester.id,
        'semester_number': section.semester.semester_number,
        'academic_year': section.semester.curriculum.academic_year,
        'capacity': section.capacity,
        'is_active': section.is_active,
    })


@admin_required_api
@login_required(login_url='login')
@require_POST
def section_delete_ajax(request, pk):
    section = get_object_or_404(Section, pk=pk)
    name = section.name
    section.delete()
    messages.success(request, f'Section "{name}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})
