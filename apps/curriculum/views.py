import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db.models import Q
from django.db import IntegrityError

from apps.program.models import Program
from apps.users.decorators import admin_required, admin_required_api

from .models import Curriculum, Semester


@login_required(login_url='login')
@admin_required
def curriculum_list(request):
    query = request.GET.get('q', '').strip()
    curricula = (
        Curriculum.objects.select_related('program')
        .prefetch_related('semesters')
        .all()
    )
    if query:
        curricula = curricula.filter(
            Q(code__icontains=query) |
            Q(name__icontains=query) |
            Q(program__program_code__icontains=query) |
            Q(program__program_description__icontains=query) |
            Q(academic_year__icontains=query)
        )
    paginator = Paginator(curricula, 10)
    page_number = request.GET.get('page', 1)
    curricula = paginator.get_page(page_number)
    programs = Program.objects.filter(is_active=True).order_by('program_code')
    return render(request, 'curriculum_list.html', {
        'curricula': curricula,
        'programs': programs,
        'query': query,
    })


@login_required(login_url='login')
@admin_required_api
@require_POST
def curriculum_save_ajax(request):
    curriculum_id = request.POST.get('id')
    if curriculum_id:
        curriculum = get_object_or_404(Curriculum, pk=curriculum_id)
    else:
        curriculum = Curriculum()

    code = request.POST.get('code', '').strip()
    name = request.POST.get('name', '').strip()
    program_id = request.POST.get('program', '').strip()
    academic_year = request.POST.get('academic_year', '').strip()
    is_active = request.POST.get('is_active') == 'true'

    if not code:
        return JsonResponse({'error': 'Curriculum code is required.'}, status=400)
    if not name:
        return JsonResponse({'error': 'Curriculum name is required.'}, status=400)
    if not program_id:
        return JsonResponse({'error': 'Program is required.'}, status=400)
    if not academic_year:
        return JsonResponse({'error': 'Academic year is required.'}, status=400)

    if not re.match(r'^[0-9]{4}-[0-9]{4}$', academic_year):
        return JsonResponse({'error': 'Academic year must be in YYYY-YYYY format.'}, status=400)

    try:
        program = Program.objects.get(pk=int(program_id))
    except (Program.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid program.'}, status=400)

    dup_qs = Curriculum.objects.filter(Q(code=code) | Q(name=name))
    if curriculum_id:
        dup_qs = dup_qs.exclude(pk=curriculum_id)
    if dup_qs.filter(code=code).exists():
        return JsonResponse({'error': 'That curriculum code is already taken.'}, status=400)
    if dup_qs.filter(name=name).exists():
        return JsonResponse({'error': 'That curriculum name is already in use.'}, status=400)

    curriculum.code = code
    curriculum.name = name
    curriculum.program = program
    curriculum.academic_year = academic_year
    curriculum.is_active = is_active

    try:
        curriculum.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save curriculum due to a conflict.'}, status=400)

    messages.success(request, f'Curriculum "{curriculum.code}" has been saved successfully.')
    return JsonResponse({
        'status': 'success',
        'id': curriculum.id,
        'code': curriculum.code,
        'name': curriculum.name,
        'program': curriculum.program.id,
        'program_name': str(curriculum.program),
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
    code = curriculum.code
    curriculum.delete()
    messages.success(request, f'Curriculum "{code}" has been deleted successfully.')
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

    if semester_number not in (1, 2):
        return JsonResponse({'error': 'Semester number must be 1 or 2.'}, status=400)

    try:
        curriculum = Curriculum.objects.get(pk=int(curriculum_id))
    except (Curriculum.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid curriculum.'}, status=400)

    dup_qs = Semester.objects.filter(curriculum=curriculum, semester_number=semester_number)
    if semester_id:
        dup_qs = dup_qs.exclude(pk=semester_id)
    if dup_qs.exists():
        return JsonResponse(
            {'error': f'Semester {semester_number} already exists for this curriculum.'},
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
        f'Semester {semester.semester_number} for {curriculum.code} has been saved successfully.',
    )
    return JsonResponse({
        'status': 'success',
        'id': semester.id,
        'curriculum': curriculum.id,
        'curriculum_code': curriculum.code,
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

    curriculum_code = semester.curriculum.code
    semester_number = semester.semester_number
    semester.delete()
    messages.success(
        request,
        f'Semester {semester_number} for {curriculum_code} has been deleted successfully.',
    )
    return JsonResponse({'status': 'deleted'})


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
        f'Active curriculum set to {semester.curriculum.code} — '
        f'Semester {semester.semester_number}.',
    )
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))
