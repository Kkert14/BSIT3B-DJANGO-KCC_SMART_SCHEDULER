from django.shortcuts import redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db import IntegrityError

from apps.curriculum.models import Semester
from apps.program.models import Program
from .models import Subject
from apps.users.decorators import admin_required_api


@login_required(login_url='login')
def subject_list_page(request):
    """Courses are managed per program on the Programs page."""
    return redirect('program:program_list')


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
    lecture_hours = request.POST.get('lecture_hours', '').strip() or '0'
    lab_hours = request.POST.get('lab_hours', '').strip() or '0'
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
        return JsonResponse({'error': 'Course code is required.'}, status=400)
    if not name:
        return JsonResponse({'error': 'Course name is required.'}, status=400)
    if not units:
        return JsonResponse({'error': 'Units is required.'}, status=400)
    try:
        units = float(units)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Units must be a number.'}, status=400)
    try:
        lecture_hours = int(lecture_hours)
        lab_hours = int(lab_hours)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Lecture and lab hours must be numbers.'}, status=400)
    if lecture_hours < 0 or lab_hours < 0:
        return JsonResponse({'error': 'Hours cannot be negative.'}, status=400)
    if lecture_hours + lab_hours == 0:
        return JsonResponse({'error': 'Enter lecture or lab hours.'}, status=400)
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
            return JsonResponse({'error': 'Invalid prerequisite course.'}, status=400)
        if prerequisite == subject:
            return JsonResponse({'error': 'A course cannot be its own prerequisite.'}, status=400)

    dup_qs = Subject.objects.filter(
        program=program, code=code, semester=semester
    )
    if subject_id:
        dup_qs = dup_qs.exclude(pk=subject_id)
    if dup_qs.exists():
        return JsonResponse({'error': 'A course with this code already exists in this program/semester.'}, status=400)

    subject.program = program
    subject.code = code
    subject.name = name
    subject.units = units
    subject.lecture_hours = lecture_hours
    subject.lab_hours = lab_hours
    subject.semester = semester
    subject.year_level = year_level
    subject.prerequisite = prerequisite

    try:
        subject.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save course due to a conflict.'}, status=400)

    messages.success(request, f'Course "{subject.code}" has been saved successfully.')
    return JsonResponse({
        'status': 'success',
        'id': subject.id,
        'program': subject.program.id,
        'program_name': str(subject.program),
        'code': subject.code,
        'name': subject.name,
        'units': str(subject.units),
        'lecture_hours': subject.lecture_hours,
        'lab_hours': subject.lab_hours,
        'total_hours': subject.total_hours,
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
    messages.success(request, f'Course "{code}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})


