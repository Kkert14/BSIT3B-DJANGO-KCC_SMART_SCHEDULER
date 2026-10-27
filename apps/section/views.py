from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError

from apps.program.models import Program
from .models import Section
from apps.users.decorators import admin_required, admin_required_api
from apps.utils.import_export import (
    excel_to_dict_list,
    get_str,
    get_value,
    parse_bool,
    parse_time,
    queryset_to_excel,
    workbook_to_response,
)


@login_required(login_url='login')
def section_list_page(request):
    query = request.GET.get('q', '').strip()
    sections_list = Section.objects.select_related('program').all()
    if query:
        sections_list = sections_list.filter(
            Q(name__icontains=query) |
            Q(program__code__icontains=query) |
            Q(program__name__icontains=query) |
            Q(academic_year__icontains=query)
        )
    paginator = Paginator(sections_list, 10)
    page_number = request.GET.get('page', 1)
    sections = paginator.get_page(page_number)
    programs = Program.objects.filter(is_active=True).order_by('code')
    return render(request, 'section_list.html', {
        'sections': sections,
        'query': query,
        'programs': programs,
    })


@login_required(login_url='login')
def section_list_ajax(request):
    query = request.GET.get('q', '').strip()
    sections_list = Section.objects.select_related('program').all()
    if query:
        sections_list = sections_list.filter(
            Q(name__icontains=query) |
            Q(program__code__icontains=query) |
            Q(program__name__icontains=query) |
            Q(academic_year__icontains=query)
        )
    paginator = Paginator(sections_list, 10)
    page_number = request.GET.get('page', 1)
    sections = paginator.get_page(page_number)
    data = list(sections.object_list.values(
        'id', 'name', 'year_level', 'academic_year', 'capacity', 'is_active', 'program_id',
    ))
    for item in data:
        program = Program.objects.filter(pk=item.pop('program_id')).first()
        item['program'] = str(program) if program else ''
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
    section = get_object_or_404(Section.objects.select_related('program'), pk=pk)
    return JsonResponse({
        'id': section.id,
        'program': section.program.id,
        'program_name': str(section.program),
        'name': section.name,
        'year_level': section.year_level,
        'academic_year': section.academic_year,
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
    academic_year = request.POST.get('academic_year', '').strip()
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
    if not academic_year:
        return JsonResponse({'error': 'Academic year is required.'}, status=400)
    if not capacity:
        return JsonResponse({'error': 'Capacity is required.'}, status=400)
    try:
        capacity = int(capacity)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Capacity must be a number.'}, status=400)

    dup_qs = Section.objects.filter(
        academic_year=academic_year, program=program, year_level=year_level, name=name
    )
    if section_id:
        dup_qs = dup_qs.exclude(pk=section_id)
    if dup_qs.exists():
        return JsonResponse({'error': 'A section with this identity already exists.'}, status=400)

    section.program = program
    section.name = name
    section.year_level = year_level
    section.academic_year = academic_year
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
        'academic_year': section.academic_year,
        'capacity': section.capacity,
        'is_active': section.is_active,
    })


@login_required(login_url='login')
@admin_required
def section_export_excel(request):
    sections = Section.objects.select_related('program').all().order_by('program__code', 'name')
    wb = queryset_to_excel(
        sections,
        ['program__code', 'name', 'year_level', 'academic_year', 'capacity', 'is_active'],
        sheet_name='Sections',
        title='Sections Export',
    )
    return workbook_to_response(wb, 'sections_export.xlsx')


@admin_required_api
@login_required(login_url='login')
@require_POST
def section_import_excel(request):
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No file uploaded.'}, status=400)

    uploaded_file = request.FILES['file']
    try:
        data = excel_to_dict_list(uploaded_file.read())
    except Exception as e:
        return JsonResponse({'error': f'Failed to read file: {str(e)}'}, status=400)

    created = 0
    errors = []
    for idx, row in enumerate(data, start=2):
        program_code = get_str(row, 'program_code')
        name = get_str(row, 'name')
        year_level = get_str(row, 'year_level')
        academic_year = get_str(row, 'academic_year')
        capacity = get_str(row, 'capacity')
        is_active = parse_bool(get_value(row, 'is_active'))

        if not program_code or not name or not year_level or not academic_year:
            errors.append(f'Row {idx}: program_code, name, year_level, and academic_year are required.')
            continue

        try:
            program = Program.objects.get(code=program_code)
        except Program.DoesNotExist:
            errors.append(f'Row {idx}: program with code "{program_code}" not found.')
            continue

        try:
            year_level_val = int(year_level)
        except ValueError:
            errors.append(f'Row {idx}: year_level must be a number.')
            continue

        try:
            capacity_val = int(capacity) if capacity else 1
        except ValueError:
            errors.append(f'Row {idx}: capacity must be a number.')
            continue

        try:
            section, created_flag = Section.objects.update_or_create(
                program=program,
                name=name,
                academic_year=academic_year,
                defaults={
                    'year_level': year_level_val,
                    'capacity': capacity_val,
                    'is_active': is_active,
                },
            )
            if created_flag:
                created += 1
        except Exception as e:
            errors.append(f'Row {idx}: {str(e)}')

    return JsonResponse({
        'status': 'success',
        'created': created,
        'errors': errors,
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
