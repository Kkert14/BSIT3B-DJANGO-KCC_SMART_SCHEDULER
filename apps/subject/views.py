from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError

from apps.program.models import Program
from .models import Subject


@login_required(login_url='login')
def subject_list_page(request):
    query = request.GET.get('q', '').strip()
    subjects_list = Subject.objects.select_related('program', 'prerequisite').all()
    if query:
        subjects_list = subjects_list.filter(
            Q(code__icontains=query) |
            Q(name__icontains=query) |
            Q(program__code__icontains=query)
        )
    paginator = Paginator(subjects_list, 10)
    page_number = request.GET.get('page', 1)
    subjects = paginator.get_page(page_number)
    programs = Program.objects.filter(is_active=True).order_by('code')
    all_subjects = Subject.objects.all().order_by('code')
    return render(request, 'subject_list.html', {
        'subjects': subjects,
        'query': query,
        'programs': programs,
        'all_subjects': all_subjects,
    })


@login_required(login_url='login')
def subject_list_ajax(request):
    query = request.GET.get('q', '').strip()
    subjects_list = Subject.objects.select_related('program', 'prerequisite').all()
    if query:
        subjects_list = subjects_list.filter(
            Q(code__icontains=query) |
            Q(name__icontains=query) |
            Q(program__code__icontains=query)
        )
    paginator = Paginator(subjects_list, 10)
    page_number = request.GET.get('page', 1)
    subjects = paginator.get_page(page_number)
    data = list(subjects.object_list.values(
        'id', 'code', 'name', 'units', 'lec_hours', 'lab_hours',
        'program_id', 'academic_year', 'year_level', 'semester',
        'prerequisite_id',
    ))
    for item in data:
        program = Program.objects.filter(pk=item.pop('program_id')).first()
        item['program'] = str(program) if program else ''
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
    subject = get_object_or_404(Subject.objects.select_related('program', 'prerequisite'), pk=pk)
    return JsonResponse({
        'id': subject.id,
        'program': subject.program.id,
        'program_name': str(subject.program),
        'code': subject.code,
        'name': subject.name,
        'units': str(subject.units),
        'lec_hours': subject.lec_hours,
        'lab_hours': subject.lab_hours,
        'academic_year': subject.academic_year,
        'year_level': subject.year_level,
        'semester': subject.semester,
        'prerequisite': subject.prerequisite.id if subject.prerequisite else None,
        'prerequisite_name': str(subject.prerequisite) if subject.prerequisite else None,
    })


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
    lec_hours = request.POST.get('lec_hours', '').strip()
    lab_hours = request.POST.get('lab_hours', '').strip()
    academic_year = request.POST.get('academic_year', '').strip()
    year_level = request.POST.get('year_level', '').strip()
    semester = request.POST.get('semester', '').strip()
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
    try:
        lec_hours = int(lec_hours) if lec_hours else 0
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Lecture hours must be a number.'}, status=400)
    try:
        lab_hours = int(lab_hours) if lab_hours else 0
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Laboratory hours must be a number.'}, status=400)
    if not academic_year:
        return JsonResponse({'error': 'Academic year is required.'}, status=400)
    if not year_level:
        return JsonResponse({'error': 'Year level is required.'}, status=400)
    try:
        year_level = int(year_level)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Year level must be a number.'}, status=400)
    if not semester:
        return JsonResponse({'error': 'Semester is required.'}, status=400)
    try:
        semester = int(semester)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Semester must be a number.'}, status=400)

    prerequisite = None
    if prerequisite_id:
        try:
            prerequisite = Subject.objects.get(pk=int(prerequisite_id))
        except (Subject.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'error': 'Invalid prerequisite subject.'}, status=400)
        if prerequisite == subject:
            return JsonResponse({'error': 'A subject cannot be its own prerequisite.'}, status=400)

    dup_qs = Subject.objects.filter(
        program=program, code=code, academic_year=academic_year, semester=semester
    )
    if subject_id:
        dup_qs = dup_qs.exclude(pk=subject_id)
    if dup_qs.exists():
        return JsonResponse({'error': 'A subject with this code already exists in this program/year/semester.'}, status=400)

    subject.program = program
    subject.code = code
    subject.name = name
    subject.units = units
    subject.lec_hours = lec_hours
    subject.lab_hours = lab_hours
    subject.academic_year = academic_year
    subject.year_level = year_level
    subject.semester = semester
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
        'lec_hours': subject.lec_hours,
        'lab_hours': subject.lab_hours,
        'academic_year': subject.academic_year,
        'year_level': subject.year_level,
        'semester': subject.semester,
        'prerequisite': subject.prerequisite.id if subject.prerequisite else None,
        'prerequisite_name': str(subject.prerequisite) if subject.prerequisite else None,
    })


@login_required(login_url='login')
@require_POST
def subject_delete_ajax(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    code = subject.code
    subject.delete()
    messages.success(request, f'Subject "{code}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})
