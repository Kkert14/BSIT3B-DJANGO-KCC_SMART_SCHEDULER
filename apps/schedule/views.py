from datetime import datetime, timedelta

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError

from apps.teacher.models import Teacher
from apps.subject.models import Subject
from apps.section.models import Section
from apps.rooms.models import Room
from .models import Schedule


def _parse_time(raw):
    """Convert 'HH:MM' string to a datetime.time, or None when invalid."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%H:%M').time()
    except (ValueError, TypeError):
        return None


def _time_duration_hours(start, end):
    """Return the duration between two time values in hours (float)."""
    dummy = datetime(2000, 1, 1)
    return (datetime.combine(dummy, end) - datetime.combine(dummy, start)).total_seconds() / 3600.0


def _check_schedule_conflicts(academic_year, semester, teacher, subject, section, room,
                              class_type, day_of_week, start_time, end_time, exclude_id=None):
    """Validate scheduling conflicts. Returns an error dict or None."""
    # end_time must be after start_time
    if end_time <= start_time:
        return {'error': 'End time must be after start time.', 'status': 400}

    base_qs = Schedule.objects.filter(
        academic_year=academic_year,
        semester=semester,
        day_of_week=day_of_week,
    )
    if exclude_id:
        base_qs = base_qs.exclude(pk=exclude_id)

    # Teacher double-booking (identical or overlapping slot)
    teacher_clashes = base_qs.filter(teacher=teacher).filter(
        Q(start_time__lt=end_time) & Q(end_time__gt=start_time)
    )
    if teacher_clashes.exists():
        clash = teacher_clashes.first()
        return {
            'error': (
                f'Teacher "{teacher}" is already scheduled for '
                f'{clash.subject} ({clash.section}) on {clash.get_day_of_week_display()} '
                f'{clash.start_time}-{clash.end_time}.'
            ),
            'status': 400,
        }

    # Room double-booking
    room_clashes = base_qs.filter(room=room).filter(
        Q(start_time__lt=end_time) & Q(end_time__gt=start_time)
    )
    if room_clashes.exists():
        clash = room_clashes.first()
        return {
            'error': (
                f'Room "{room}" is already scheduled for '
                f'{clash.subject} ({clash.section}) on {clash.get_day_of_week_display()} '
                f'{clash.start_time}-{clash.end_time}.'
            ),
            'status': 400,
        }

    # Section double-booking
    section_clashes = base_qs.filter(section=section).filter(
        Q(start_time__lt=end_time) & Q(end_time__gt=start_time)
    )
    if section_clashes.exists():
        clash = section_clashes.first()
        return {
            'error': (
                f'Section "{section}" is already scheduled for '
                f'{clash.subject} with {clash.teacher} on {clash.get_day_of_week_display()} '
                f'{clash.start_time}-{clash.end_time}.'
            ),
            'status': 400,
        }

    # Subject time limit per section (Lecture / Laboratory)
    existing_same = Schedule.objects.filter(
        academic_year=academic_year,
        semester=semester,
        subject=subject,
        section=section,
        class_type=class_type,
    )
    if exclude_id:
        existing_same = existing_same.exclude(pk=exclude_id)

    total_hours = sum(
        _time_duration_hours(s.start_time, s.end_time) for s in existing_same
    )
    total_hours += _time_duration_hours(start_time, end_time)

    limit = subject.lec_hours if class_type == 'Lecture' else subject.lab_hours
    if total_hours > limit:
        return {
            'error': (
                f'Total {class_type.lower()} time ({total_hours:.1f}h) would exceed the '
                f'allowed {subject.lab_hours if class_type == "Laboratory" else subject.lec_hours}h '
                f'for subject "{subject}" in section "{section}".'
            ),
            'status': 400,
        }

    return None


@login_required(login_url='login')
def schedule_list_page(request):
    query = request.GET.get('q', '').strip()
    schedules_list = Schedule.objects.select_related(
        'teacher', 'subject', 'section', 'room'
    ).all()
    if query:
        schedules_list = schedules_list.filter(
            Q(subject__code__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(section__name__icontains=query) |
            Q(teacher__first_name__icontains=query) |
            Q(teacher__last_name__icontains=query) |
            Q(room__room_name__icontains=query) |
            Q(academic_year__icontains=query)
        )
    paginator = Paginator(schedules_list, 10)
    page_number = request.GET.get('page', 1)
    schedules = paginator.get_page(page_number)
    teachers = Teacher.objects.filter(is_active=True).order_by('last_name', 'first_name')
    subjects = Subject.objects.all().order_by('code')
    sections = Section.objects.filter(is_active=True).order_by('name')
    rooms = Room.objects.filter(is_active=True).order_by('building__code', 'room_name')
    return render(request, 'schedule_list.html', {
        'schedules': schedules,
        'query': query,
        'teachers': teachers,
        'subjects': subjects,
        'sections': sections,
        'rooms': rooms,
    })


@login_required(login_url='login')
def schedule_list_ajax(request):
    query = request.GET.get('q', '').strip()
    schedules_list = Schedule.objects.select_related(
        'teacher', 'subject', 'section', 'room'
    ).all()
    if query:
        schedules_list = schedules_list.filter(
            Q(subject__code__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(section__name__icontains=query) |
            Q(teacher__first_name__icontains=query) |
            Q(teacher__last_name__icontains=query) |
            Q(room__room_name__icontains=query) |
            Q(academic_year__icontains=query)
        )
    paginator = Paginator(schedules_list, 10)
    page_number = request.GET.get('page', 1)
    schedules = paginator.get_page(page_number)
    data = list(schedules.object_list.values(
        'id', 'academic_year', 'semester', 'class_type', 'day_of_week',
        'start_time', 'end_time', 'teacher_id', 'subject_id', 'section_id', 'room_id',
    ))
    for item in data:
        tid = item.pop('teacher_id')
        sid = item.pop('subject_id')
        sec_id = item.pop('section_id')
        rid = item.pop('room_id')
        teacher = Teacher.objects.filter(pk=tid).first()
        subject = Subject.objects.filter(pk=sid).first()
        section = Section.objects.filter(pk=sec_id).first()
        room = Room.objects.filter(pk=rid).first()
        item['teacher'] = str(teacher) if teacher else ''
        item['subject'] = str(subject) if subject else ''
        item['section'] = str(section) if section else ''
        item['room'] = str(room) if room else ''
        item['start_time'] = item['start_time'].strftime('%H:%M') if item['start_time'] else ''
        item['end_time'] = item['end_time'].strftime('%H:%M') if item['end_time'] else ''
    return JsonResponse({
        'data': data,
        'has_next': schedules.has_next(),
        'has_prev': schedules.has_previous(),
        'page': schedules.number,
        'pages': schedules.paginator.num_pages,
        'total': schedules.paginator.count,
    })


@login_required(login_url='login')
def schedule_get_ajax(request, pk):
    schedule = get_object_or_404(
        Schedule.objects.select_related('teacher', 'subject', 'section', 'room'), pk=pk
    )
    return JsonResponse({
        'id': schedule.id,
        'academic_year': schedule.academic_year,
        'semester': schedule.semester,
        'teacher': schedule.teacher.id,
        'teacher_name': str(schedule.teacher),
        'subject': schedule.subject.id,
        'subject_name': str(schedule.subject),
        'section': schedule.section.id,
        'section_name': str(schedule.section),
        'room': schedule.room.id,
        'room_name': str(schedule.room),
        'class_type': schedule.class_type,
        'day_of_week': schedule.day_of_week,
        'start_time': schedule.start_time.strftime('%H:%M'),
        'end_time': schedule.end_time.strftime('%H:%M'),
    })


@login_required(login_url='login')
@require_POST
def schedule_save_ajax(request):
    schedule_id = request.POST.get('id')
    if schedule_id:
        schedule = get_object_or_404(Schedule, pk=schedule_id)
    else:
        schedule = Schedule()

    academic_year = request.POST.get('academic_year', '').strip()
    semester = request.POST.get('semester', '').strip()
    teacher_id = request.POST.get('teacher', '').strip()
    subject_id = request.POST.get('subject', '').strip()
    section_id = request.POST.get('section', '').strip()
    room_id = request.POST.get('room', '').strip()
    class_type = request.POST.get('class_type', '').strip()
    day_of_week = request.POST.get('day_of_week', '').strip()
    start_time = _parse_time(request.POST.get('start_time', ''))
    end_time = _parse_time(request.POST.get('end_time', ''))

    if not academic_year:
        return JsonResponse({'error': 'Academic year is required.'}, status=400)
    if not semester:
        return JsonResponse({'error': 'Semester is required.'}, status=400)
    try:
        semester = int(semester)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Semester must be a number.'}, status=400)

    try:
        teacher = Teacher.objects.get(pk=int(teacher_id))
    except (Teacher.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid teacher.'}, status=400)
    try:
        subject = Subject.objects.get(pk=int(subject_id))
    except (Subject.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid subject.'}, status=400)
    try:
        section = Section.objects.get(pk=int(section_id))
    except (Section.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid section.'}, status=400)
    try:
        room = Room.objects.get(pk=int(room_id))
    except (Room.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid room.'}, status=400)

    if class_type not in ('Lecture', 'Laboratory'):
        return JsonResponse({'error': 'Class type must be Lecture or Laboratory.'}, status=400)
    if not day_of_week:
        return JsonResponse({'error': 'Day of week is required.'}, status=400)
    try:
        day_of_week = int(day_of_week)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Day of week must be a number.'}, status=400)
    if not start_time:
        return JsonResponse({'error': 'Start time is required.'}, status=400)
    if not end_time:
        return JsonResponse({'error': 'End time is required.'}, status=400)

    conflict = _check_schedule_conflicts(
        academic_year, semester, teacher, subject, section, room,
        class_type, day_of_week, start_time, end_time,
        exclude_id=schedule.id if schedule.pk else None,
    )
    if conflict:
        return JsonResponse(conflict, status=conflict['status'])

    schedule.academic_year = academic_year
    schedule.semester = semester
    schedule.teacher = teacher
    schedule.subject = subject
    schedule.section = section
    schedule.room = room
    schedule.class_type = class_type
    schedule.day_of_week = day_of_week
    schedule.start_time = start_time
    schedule.end_time = end_time

    try:
        schedule.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save schedule due to a conflict.'}, status=400)

    messages.success(request, 'Schedule has been saved successfully.')
    return JsonResponse({
        'status': 'success',
        'id': schedule.id,
        'academic_year': schedule.academic_year,
        'semester': schedule.semester,
        'teacher': schedule.teacher.id,
        'teacher_name': str(schedule.teacher),
        'subject': schedule.subject.id,
        'subject_name': str(schedule.subject),
        'section': schedule.section.id,
        'section_name': str(schedule.section),
        'room': schedule.room.id,
        'room_name': str(schedule.room),
        'class_type': schedule.class_type,
        'day_of_week': schedule.day_of_week,
        'start_time': schedule.start_time.strftime('%H:%M'),
        'end_time': schedule.end_time.strftime('%H:%M'),
    })


@login_required(login_url='login')
@require_POST
def schedule_delete_ajax(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk)
    desc = f'{schedule.subject} ({schedule.section})'
    schedule.delete()
    messages.success(request, f'Schedule "{desc}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})
