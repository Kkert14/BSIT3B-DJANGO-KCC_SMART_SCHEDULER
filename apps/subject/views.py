from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError

from apps.curriculum.models import Semester
from apps.program.models import Program
from .models import Subject
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


def subject_list_context(request):
    """Context for the Courses tab of the Programs hub."""
    query = request.GET.get('q', '').strip()
    subjects_list = Subject.objects.select_related('program', 'prerequisite', 'semester__curriculum').all()
    if query:
        subjects_list = subjects_list.filter(
            Q(code__icontains=query) |
            Q(name__icontains=query) |
            Q(program__program_code__icontains=query) |
            Q(semester__curriculum__academic_year__icontains=query)
        )
    paginator = Paginator(subjects_list, 10)
    page_number = request.GET.get('page', 1)
    subjects = paginator.get_page(page_number)
    programs = Program.objects.filter(is_active=True).order_by('program_code')
    semesters = Semester.objects.select_related('curriculum').all().order_by('curriculum__academic_year', 'semester_number')
    all_subjects = Subject.objects.all().order_by('code')
    return {
        'subjects': subjects,
        'query': query,
        'programs': programs,
        'semesters': semesters,
        'all_subjects': all_subjects,
    }


@login_required(login_url='login')
def subject_list_page(request):
    url = f"{reverse('program:program_list')}?tab=courses"
    extra = request.GET.urlencode()
    if extra:
        url = f'{url}&{extra}'
    return redirect(url)


@login_required(login_url='login')
def subject_list_ajax(request):
    query = request.GET.get('q', '').strip()
    subjects_list = Subject.objects.select_related('program', 'prerequisite', 'semester__curriculum').all()
    if query:
        subjects_list = subjects_list.filter(
            Q(code__icontains=query) |
            Q(name__icontains=query) |
            Q(program__program_code__icontains=query) |
            Q(semester__curriculum__academic_year__icontains=query)
        )
    paginator = Paginator(subjects_list, 10)
    page_number = request.GET.get('page', 1)
    subjects = paginator.get_page(page_number)
    data = list(subjects.object_list.values(
        'id', 'code', 'name', 'units', 'total_hours', 'is_lab',
        'program_id', 'semester_id', 'year_level',
        'prerequisite_id',
    ))
    for item in data:
        program = Program.objects.filter(pk=item.pop('program_id')).first()
        item['program'] = str(program) if program else ''
        semester = Semester.objects.filter(pk=item.pop('semester_id')).first()
        item['semester'] = str(semester) if semester else ''
        item['semester_number'] = semester.semester_number if semester else None
        item['academic_year'] = semester.curriculum.academic_year if semester else ''
        prereq_id = item.pop('prerequisite_id')
        if prereq_id:
            prereq = Subject.objects.filter(pk=prereq_id).first()
            item['prerequisite'] = str(prereq) if prereq else None
        else:
            item['prerequisite'] = None
    return JsonResponse({
        'data': data,
        'has_next': subjects.has_next(),
        'has_prev': subjects.has_previous(),
        'page': subjects.number,
        'pages': subjects.paginator.num_pages,
        'total': subjects.paginator.count,
    })


@login_required(login_url='login')
def subject_get_ajax(request, pk):
    subject = get_object_or_404(Subject.objects.select_related('program', 'prerequisite', 'semester__curriculum'), pk=pk)
    return JsonResponse({
        'id': subject.id,
        'program': subject.program.id,
        'program_name': str(subject.program),
        'code': subject.code,
        'name': subject.name,
        'units': str(subject.units),
        'total_hours': subject.total_hours,
        'is_lab': subject.is_lab,
        'semester': subject.semester.id,
        'semester_number': subject.semester.semester_number,
        'academic_year': subject.semester.curriculum.academic_year,
        'year_level': subject.year_level,
        'prerequisite': subject.prerequisite.id if subject.prerequisite else None,
        'prerequisite_name': str(subject.prerequisite) if subject.prerequisite else None,
    })


@admin_required_api
@login_required(login_url='login')
@require_POST
def subject_save_ajax(request):
    subject_id = request.POST.get('id')
    if subject_id:
        subject = get_object_or_404(Subject, pk=subject_id)
    else:
        subject = Subject()

    program_id = request.POST.get('program')
    code = request.POST.get('code', '').strip()
    name = request.POST.get('name', '').strip()
    units = request.POST.get('units', '').strip()
    total_hours = request.POST.get('total_hours', '').strip()
    is_lab = request.POST.get('is_lab') == 'true'
    semester_id = request.POST.get('semester', '').strip()
    year_level = request.POST.get('year_level', '').strip()
    prerequisite_id = request.POST.get('prerequisite', '').strip()

    if not program_id:
        return JsonResponse({'error': 'Program is required.'}, status=400)
    try:
        program = Program.objects.get(pk=int(program_id))
    except (Program.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid program.'}, status=400)

    if not code:
        return JsonResponse({'error': 'Subject code is required.'}, status=400)
    if not name:
        return JsonResponse({'error': 'Subject name is required.'}, status=400)
    if not units:
        return JsonResponse({'error': 'Units is required.'}, status=400)
    try:
        units = float(units)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Units must be a number.'}, status=400)
    if not total_hours:
        return JsonResponse({'error': 'Total hours is required.'}, status=400)
    try:
        total_hours = int(total_hours)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Total hours must be a number.'}, status=400)
    if not semester_id:
        return JsonResponse({'error': 'Semester is required.'}, status=400)
    try:
        semester = Semester.objects.get(pk=int(semester_id))
    except (Semester.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid semester.'}, status=400)
    if not year_level:
        return JsonResponse({'error': 'Year level is required.'}, status=400)
    try:
        year_level = int(year_level)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Year level must be a number.'}, status=400)

    prerequisite = None
    if prerequisite_id:
        try:
            prerequisite = Subject.objects.get(pk=int(prerequisite_id))
        except (Subject.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'error': 'Invalid prerequisite subject.'}, status=400)
        if prerequisite == subject:
            return JsonResponse({'error': 'A subject cannot be its own prerequisite.'}, status=400)

    dup_qs = Subject.objects.filter(
        program=program, code=code, semester=semester
    )
    if subject_id:
        dup_qs = dup_qs.exclude(pk=subject_id)
    if dup_qs.exists():
        return JsonResponse({'error': 'A subject with this code already exists in this program/semester.'}, status=400)

    subject.program = program
    subject.code = code
    subject.name = name
    subject.units = units
    subject.total_hours = total_hours
    subject.is_lab = is_lab
    subject.semester = semester
    subject.year_level = year_level
    subject.prerequisite = prerequisite

    try:
        subject.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save subject due to a conflict.'}, status=400)

    messages.success(request, f'Subject "{subject.code}" has been saved successfully.')
    return JsonResponse({
        'status': 'success',
        'id': subject.id,
        'program': subject.program.id,
        'program_name': str(subject.program),
        'code': subject.code,
        'name': subject.name,
        'units': str(subject.units),
        'total_hours': subject.total_hours,
        'is_lab': subject.is_lab,
        'semester': subject.semester.id,
        'semester_number': subject.semester.semester_number,
        'academic_year': subject.semester.curriculum.academic_year,
        'year_level': subject.year_level,
        'prerequisite': subject.prerequisite.id if subject.prerequisite else None,
        'prerequisite_name': str(subject.prerequisite) if subject.prerequisite else None,
    })


@admin_required_api
@login_required(login_url='login')
@require_POST
def subject_delete_ajax(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    code = subject.code
    subject.delete()
    messages.success(request, f'Subject "{code}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})


@login_required(login_url='login')
@admin_required
def subject_export_excel(request):
    subjects = Subject.objects.select_related('program', 'prerequisite', 'semester__curriculum').all().order_by('program__program_code', 'code')
    wb = queryset_to_excel(
        subjects,
        ['program__program_code', 'code', 'name', 'units', 'total_hours', 'is_lab', 'semester__curriculum__academic_year', 'semester__semester_number', 'year_level', 'semester__curriculum__code', 'prerequisite__code'],
        sheet_name='Subjects',
        title='Subjects Export',
    )
    return workbook_to_response(wb, 'subjects_export.xlsx')


@admin_required_api
@login_required(login_url='login')
@require_POST
def subject_import_excel(request):
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
        program_code = get_str(row, 'program_program_code')
        code = get_str(row, 'code')
        name = get_str(row, 'name')
        units = get_str(row, 'units')
        total_hours = get_str(row, 'total_hours')
        is_lab = parse_bool(get_value(row, 'is_lab'), default=False)
        curriculum_code = get_str(row, 'semester_curriculum_code')
        semester_number = get_str(row, 'semester_semester_number')
        year_level = get_str(row, 'year_level')
        prereq_code = get_str(row, 'prerequisite_code')

        if not program_code or not code or not name or not units or not total_hours or not curriculum_code or not semester_number or not year_level:
            errors.append(f'Row {idx}: program_program_code, code, name, units, total_hours, semester_curriculum_code, semester_semester_number, and year_level are required.')
            continue

        try:
            program = Program.objects.get(program_code=program_code)
        except Program.DoesNotExist:
            errors.append(f'Row {idx}: program with code "{program_code}" not found.')
            continue

        try:
            semester = Semester.objects.get(curriculum__code=curriculum_code, semester_number=int(semester_number))
        except (Semester.DoesNotExist, ValueError):
            errors.append(f'Row {idx}: semester {semester_number} in curriculum "{curriculum_code}" not found.')
            continue

        try:
            units_val = float(units)
        except ValueError:
            errors.append(f'Row {idx}: units must be a number.')
            continue

        try:
            total_hours_val = int(total_hours)
        except ValueError:
            errors.append(f'Row {idx}: total_hours must be a number.')
            continue

        try:
            year_level_val = int(year_level)
        except ValueError:
            errors.append(f'Row {idx}: year_level must be a number.')
            continue

        prerequisite = None
        if prereq_code:
            try:
                prerequisite = Subject.objects.get(code=prereq_code, program=program)
            except Subject.DoesNotExist:
                errors.append(f'Row {idx}: prerequisite subject "{prereq_code}" not found in program "{program_code}".')
                continue

        try:
            subject, created_flag = Subject.objects.update_or_create(
                program=program,
                code=code,
                semester=semester,
                defaults={
                    'name': name,
                    'units': units_val,
                    'total_hours': total_hours_val,
                    'is_lab': is_lab,
                    'year_level': year_level_val,
                    'prerequisite': prerequisite,
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
