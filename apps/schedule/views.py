from datetime import datetime, timedelta

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError

from apps.curriculum.models import Semester
from apps.teacher.models import Teacher
from apps.subject.models import Subject
from apps.section.models import Section
from apps.rooms.models import Room
from apps.building.models import Building
from apps.program.models import Program
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
from .models import Schedule


def _parse_time(raw):
    """Convert 'HH:MM' string to a datetime.time, or None when invalid."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%H:%M').time()
    except (ValueError, TypeError):
        return None


DAY_NAMES = {
    1: 'Monday',
    2: 'Tuesday',
    3: 'Wednesday',
    4: 'Thursday',
    5: 'Friday',
    6: 'Saturday',
    7: 'Sunday',
}


def _time_duration_hours(start, end):
    """Return the duration between two time values in hours (float)."""
    dummy = datetime(2000, 1, 1)
    return (datetime.combine(dummy, end) - datetime.combine(dummy, start)).total_seconds() / 3600.0


def _check_schedule_conflicts(semester, teacher, subject, section, room,
                              class_type, day_of_week, start_time, end_time, exclude_id=None):
    """Validate scheduling conflicts. Returns a dict with 'conflicts' list and 'suggestions', or None if valid."""
    conflicts = []
    suggestions = {
        'alternative_times': [],
        'alternative_rooms': [],
        'alternative_days': [],
    }

    # end_time must be after start_time
    if end_time <= start_time:
        return {
            'conflicts': [{'type': 'invalid_time', 'message': 'End time must be after start time.'}],
            'suggestions': suggestions,
            'status': 400,
        }

    base_qs = Schedule.objects.filter(
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
        for clash in teacher_clashes:
            conflicts.append({
                'type': 'teacher',
                'message': (
                    f'Teacher "{clash.teacher.first_name} {clash.teacher.last_name}" '
                    f'is already teaching "{clash.subject.code}" for section "{clash.section.name}" '
                    f'on {DAY_NAMES.get(clash.day_of_week, clash.day_of_week)} '
                    f'{clash.start_time.strftime("%H:%M")}-{clash.end_time.strftime("%H:%M")}.'
                ),
                'clash_id': clash.id,
                'clash_teacher': str(clash.teacher),
                'clash_subject': str(clash.subject),
                'clash_section': str(clash.section),
                'clash_room': str(clash.room),
                'clash_day': clash.day_of_week,
                'clash_start': clash.start_time.strftime('%H:%M'),
                'clash_end': clash.end_time.strftime('%H:%M'),
            })

    # Room double-booking
    room_clashes = base_qs.filter(room=room).filter(
        Q(start_time__lt=end_time) & Q(end_time__gt=start_time)
    )
    if room_clashes.exists():
        for clash in room_clashes:
            conflicts.append({
                'type': 'room',
                'message': (
                    f'Room "{clash.room.room_name}" ({clash.room.building.code}) '
                    f'is already used for "{clash.subject.code}" (section "{clash.section.name}") '
                    f'on {DAY_NAMES.get(clash.day_of_week, clash.day_of_week)} '
                    f'{clash.start_time.strftime("%H:%M")}-{clash.end_time.strftime("%H:%M")}.'
                ),
                'clash_id': clash.id,
                'clash_teacher': str(clash.teacher),
                'clash_subject': str(clash.subject),
                'clash_section': str(clash.section),
                'clash_room': str(clash.room),
                'clash_day': clash.day_of_week,
                'clash_start': clash.start_time.strftime('%H:%M'),
                'clash_end': clash.end_time.strftime('%H:%M'),
            })

    # Section double-booking
    section_clashes = base_qs.filter(section=section).filter(
        Q(start_time__lt=end_time) & Q(end_time__gt=start_time)
    )
    if section_clashes.exists():
        for clash in section_clashes:
            conflicts.append({
                'type': 'section',
                'message': (
                    f'Section "{clash.section.name}" is already scheduled for '
                    f'"{clash.subject.code}" with {clash.teacher.first_name} {clash.teacher.last_name} '
                    f'on {DAY_NAMES.get(clash.day_of_week, clash.day_of_week)} '
                    f'{clash.start_time.strftime("%H:%M")}-{clash.end_time.strftime("%H:%M")}.'
                ),
                'clash_id': clash.id,
                'clash_teacher': str(clash.teacher),
                'clash_subject': str(clash.subject),
                'clash_section': str(clash.section),
                'clash_room': str(clash.room),
                'clash_day': clash.day_of_week,
                'clash_start': clash.start_time.strftime('%H:%M'),
                'clash_end': clash.end_time.strftime('%H:%M'),
            })

    if conflicts:
        # Generate suggestions
        # 1. Alternative times on the same day (different slots)
        all_time_slots = [
            ('07:00', '08:00'), ('08:00', '09:00'), ('09:00', '10:00'),
            ('10:00', '11:00'), ('11:00', '12:00'), ('13:00', '14:00'),
            ('14:00', '15:00'), ('15:00', '16:00'), ('16:00', '17:00'),
        ]
        current_start = start_time.strftime('%H:%M')
        current_end = end_time.strftime('%H:%M')

        for slot_start, slot_end in all_time_slots:
            if slot_start == current_start:
                continue
            # Check if this slot is free for teacher, room, and section
            slot_conflict = base_qs.filter(
                Q(start_time__lt=datetime.strptime(slot_end, '%H:%M').time()) &
                Q(end_time__gt=datetime.strptime(slot_start, '%H:%M').time())
            ).filter(
                Q(teacher=teacher) | Q(room=room) | Q(section=section)
            )
            if not slot_conflict.exists():
                suggestions['alternative_times'].append({
                    'day': day_of_week,
                    'day_name': DAY_NAMES.get(day_of_week, str(day_of_week)),
                    'start': slot_start,
                    'end': slot_end,
                })

        # 2. Same time on different days
        for other_day in range(1, 8):
            if other_day == day_of_week:
                continue
            day_conflict = Schedule.objects.filter(
                semester=semester,
                day_of_week=other_day,
            ).filter(
                Q(start_time__lt=end_time) & Q(end_time__gt=start_time)
            ).filter(
                Q(teacher=teacher) | Q(room=room) | Q(section=section)
            )
            if not day_conflict.exists():
                suggestions['alternative_days'].append({
                    'day': other_day,
                    'day_name': DAY_NAMES.get(other_day, str(other_day)),
                    'start': current_start,
                    'end': current_end,
                })

        # 3. Alternative rooms (same building preferred, then any)
        from apps.rooms.models import Room as RoomModel
        available_rooms = RoomModel.objects.filter(is_active=True).exclude(id=room.id)
        for alt_room in available_rooms:
            room_conflict = base_qs.filter(room=alt_room).filter(
                Q(start_time__lt=end_time) & Q(end_time__gt=start_time)
            )
            if not room_conflict.exists():
                suggestions['alternative_rooms'].append({
                    'id': alt_room.id,
                    'name': alt_room.room_name,
                    'building': alt_room.building.code,
                    'capacity': alt_room.capacity,
                    'room_type': alt_room.room_type,
                })

        return {
            'conflicts': conflicts,
            'suggestions': suggestions,
            'status': 400,
        }

    # Subject time limit per section (Lecture / Laboratory)
    existing_same = Schedule.objects.filter(
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
            'conflicts': [{
                'type': 'time_limit',
                'message': (
                    f'Total {class_type.lower()} time ({total_hours:.1f}h) would exceed the '
                    f'allowed {limit}h for subject "{subject}" in section "{section}".'
                ),
            }],
            'suggestions': suggestions,
            'status': 400,
        }

    return None


@login_required(login_url='login')
def schedule_list_page(request):
    # Get filter parameters
    filter_semester = request.GET.get('semester', '').strip()
    query = request.GET.get('q', '').strip()

    # Base queryset — ALL schedules, ordered by day and time
    schedules_list = Schedule.objects.select_related(
        'teacher', 'subject', 'section', 'room', 'semester__curriculum'
    ).order_by('day_of_week', 'start_time')

    # Apply filters
    if filter_semester:
        schedules_list = schedules_list.filter(semester=filter_semester)
    if query:
        schedules_list = schedules_list.filter(
            Q(subject__code__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(section__name__icontains=query) |
            Q(teacher__first_name__icontains=query) |
            Q(teacher__last_name__icontains=query) |
            Q(room__room_name__icontains=query) |
            Q(semester__curriculum__academic_year__icontains=query)
        )

    # Get distinct semesters for the filter dropdown
    semesters = Semester.objects.select_related('curriculum').all().order_by('curriculum__academic_year', 'semester_number')

    SEMESTER_CHOICES = [
        (1, '1st Semester'),
        (2, '2nd Semester'),
        (3, 'Summer'),
    ]

    # Standard academic time slots (start_time -> end_time)
    time_slots = [
        ('07:00', '08:00'),
        ('08:00', '09:00'),
        ('09:00', '10:00'),
        ('10:00', '11:00'),
        ('11:00', '12:00'),
        ('13:00', '14:00'),
        ('14:00', '15:00'),
        ('15:00', '16:00'),
        ('16:00', '17:00'),
    ]

    DAYS = [
        (1, 'Monday'),
        (2, 'Tuesday'),
        (3, 'Wednesday'),
        (4, 'Thursday'),
        (5, 'Friday'),
        (6, 'Saturday'),
        (7, 'Sunday'),
    ]

    # Build lookup: (day_number, slot_index) -> schedule
    schedule_lookup = {}
    for s in schedules_list:
        start_str = s.start_time.strftime('%H:%M')
        for slot_idx, (slot_start, slot_end) in enumerate(time_slots):
            if slot_start <= start_str < slot_end:
                schedule_lookup[(s.day_of_week, slot_idx)] = s
                break

    # Build timetable rows: each row = one time slot with 7 day cells
    timetable_rows = []
    for slot_idx, (start, end) in enumerate(time_slots):
        cells = []
        for day_num, day_name in DAYS:
            sched = schedule_lookup.get((day_num, slot_idx))
            cells.append({
                'day_num': day_num,
                'day_name': day_name,
                'schedule': sched,
            })
        timetable_rows.append({
            'start': start,
            'end': end,
            'slot_idx': slot_idx,
            'cells': cells,
        })

    # Pagination for the list table
    paginator = Paginator(schedules_list, 10)
    page_number = request.GET.get('page', 1)
    schedules = paginator.get_page(page_number)

    # Dropdown data for edit modal
    teachers = Teacher.objects.filter(is_active=True).order_by('last_name', 'first_name')
    subjects = Subject.objects.all().order_by('code')
    sections = Section.objects.filter(is_active=True).order_by('name')
    rooms = Room.objects.filter(is_active=True).order_by('building__code', 'room_name')

    stats = {
        'total_buildings': Building.objects.count(),
        'total_programs': Program.objects.count(),
        'total_teachers': Teacher.objects.count(),
        'total_sections': Section.objects.count(),
        'total_subjects': Subject.objects.count(),
        'total_rooms': Room.objects.count(),
        'total_schedules': schedules_list.count(),
    }

    return render(request, 'schedule_list.html', {
        'timetable_rows': timetable_rows,
        'DAYS': DAYS,
        'time_slots': time_slots,
        'all_schedules': schedules_list,
        'schedules': schedules,
        'query': query,
        'teachers': teachers,
        'subjects': subjects,
        'sections': sections,
        'rooms': rooms,
        'stats': stats,
        'filter_semester': filter_semester,
        'semesters': semesters,
        'semester_choices': SEMESTER_CHOICES,
    })


@login_required(login_url='login')
def schedule_list_ajax(request):
    query = request.GET.get('q', '').strip()
    schedules_list = Schedule.objects.select_related(
        'teacher', 'subject', 'section', 'room', 'semester__curriculum'
    ).all()
    if query:
        schedules_list = schedules_list.filter(
            Q(subject__code__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(section__name__icontains=query) |
            Q(teacher__first_name__icontains=query) |
            Q(teacher__last_name__icontains=query) |
            Q(room__room_name__icontains=query) |
            Q(semester__curriculum__academic_year__icontains=query)
        )
    paginator = Paginator(schedules_list, 10)
    page_number = request.GET.get('page', 1)
    schedules = paginator.get_page(page_number)
    data = list(schedules.object_list.values(
        'id', 'semester_id', 'class_type', 'day_of_week',
        'start_time', 'end_time', 'teacher_id', 'subject_id', 'section_id', 'room_id',
    ))
    for item in data:
        tid = item.pop('teacher_id')
        sid = item.pop('subject_id')
        sec_id = item.pop('section_id')
        rid = item.pop('room_id')
        sem_id = item.pop('semester_id')
        teacher = Teacher.objects.filter(pk=tid).first()
        subject = Subject.objects.filter(pk=sid).first()
        section = Section.objects.filter(pk=sec_id).first()
        room = Room.objects.filter(pk=rid).first()
        semester = Semester.objects.filter(pk=sem_id).first()
        item['teacher'] = str(teacher) if teacher else ''
        item['subject'] = str(subject) if subject else ''
        item['section'] = str(section) if section else ''
        item['room'] = str(room) if room else ''
        item['semester'] = str(semester) if semester else ''
        item['semester_number'] = semester.semester_number if semester else None
        item['academic_year'] = semester.curriculum.academic_year if semester else ''
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
        Schedule.objects.select_related('teacher', 'subject', 'section', 'room', 'semester__curriculum'), pk=pk
    )
    return JsonResponse({
        'id': schedule.id,
        'semester': schedule.semester.id,
        'semester_number': schedule.semester.semester_number,
        'academic_year': schedule.semester.curriculum.academic_year,
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


@admin_required_api
@login_required(login_url='login')
@require_POST
def schedule_save_ajax(request):
    schedule_id = request.POST.get('id')
    if schedule_id:
        schedule = get_object_or_404(Schedule, pk=schedule_id)
    else:
        schedule = Schedule()

    semester_id = request.POST.get('semester', '').strip()
    teacher_id = request.POST.get('teacher', '').strip()
    subject_id = request.POST.get('subject', '').strip()
    section_id = request.POST.get('section', '').strip()
    room_id = request.POST.get('room', '').strip()
    class_type = request.POST.get('class_type', '').strip()
    day_of_week = request.POST.get('day_of_week', '').strip()
    start_time = _parse_time(request.POST.get('start_time', ''))
    end_time = _parse_time(request.POST.get('end_time', ''))

    if not semester_id:
        return JsonResponse({'error': 'Semester is required.'}, status=400)
    try:
        semester = Semester.objects.get(pk=int(semester_id))
    except (Semester.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid semester.'}, status=400)

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
        semester, teacher, subject, section, room,
        class_type, day_of_week, start_time, end_time,
        exclude_id=schedule.id if schedule.pk else None,
    )
    if conflict:
        return JsonResponse(conflict, status=conflict['status'])

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
        'semester': schedule.semester.id,
        'semester_number': schedule.semester.semester_number,
        'academic_year': schedule.semester.curriculum.academic_year,
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


@admin_required_api
@login_required(login_url='login')
@require_POST
def schedule_delete_ajax(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk)
    desc = f'{schedule.subject} ({schedule.section})'
    schedule.delete()
    messages.success(request, f'Schedule "{desc}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})


def _resolve_unique(queryset, description, disambiguate_hint=''):
    """Return the single row matching ``queryset``.

    Raises ``ValueError`` when nothing matches, or when the lookup is
    ambiguous. Subject codes, section names and room names repeat across
    programs and buildings, so a spreadsheet column on its own does not
    always identify a single row.
    """
    matches = list(queryset[:2])
    if not matches:
        raise ValueError(f'{description} not found.')
    if len(matches) > 1:
        hint = f' {disambiguate_hint}' if disambiguate_hint else ''
        raise ValueError(
            f'{description} is ambiguous - it matches more than one row.{hint}'
        )
    return matches[0]


@login_required(login_url='login')
@admin_required
def schedule_export_excel(request):
    schedules = Schedule.objects.select_related(
        'teacher', 'subject', 'section', 'room', 'semester__curriculum'
    ).all().order_by('day_of_week', 'start_time')
    wb = queryset_to_excel(
        schedules,
        [
            'semester__curriculum__code', 'semester__semester_number',
            'teacher__employee_number',
            'subject__code', 'subject__program__code',
            'section__name', 'section__program__code',
            'room__room_name', 'room__building__code',
            'class_type', 'day_of_week', 'start_time', 'end_time',
        ],
        sheet_name='Schedules',
        title='Schedules Export',
    )
    return workbook_to_response(wb, 'schedules_export.xlsx')


@admin_required_api
@login_required(login_url='login')
@require_POST
def schedule_import_excel(request):
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
        curriculum_code = get_str(row, 'semester_curriculum_code')
        semester_number = get_str(row, 'semester_semester_number')
        teacher_emp = get_str(row, 'teacher__employee_number')
        subject_code = get_str(row, 'subject__code')
        subject_program_code = get_str(row, 'subject__program__code')
        section_name = get_str(row, 'section__name')
        section_program_code = get_str(row, 'section__program__code')
        room_name = get_str(row, 'room__room_name')
        building_code = get_str(row, 'room__building__code')
        class_type = get_str(row, 'class_type', 'Lecture')
        day_of_week = get_str(row, 'day_of_week')
        start = parse_time(get_value(row, 'start_time'))
        end = parse_time(get_value(row, 'end_time'))

        if not all([curriculum_code, semester_number, teacher_emp, subject_code, section_name, room_name, class_type, day_of_week, start, end]):
            errors.append(f'Row {idx}: all fields are required.')
            continue

        try:
            semester_val = int(semester_number)
        except ValueError:
            errors.append(f'Row {idx}: semester must be a number.')
            continue

        try:
            semester = Semester.objects.get(curriculum__code=curriculum_code, semester_number=semester_val)
        except Semester.DoesNotExist:
            errors.append(f'Row {idx}: semester {semester_val} in curriculum "{curriculum_code}" not found.')
            continue

        try:
            teacher = Teacher.objects.get(employee_number=teacher_emp)
        except Teacher.DoesNotExist:
            errors.append(f'Row {idx}: teacher with employee number "{teacher_emp}" not found.')
            continue

        # Subject codes repeat across programs, so narrow the lookup down with
        # whichever extra columns the spreadsheet provides.
        try:
            subject_qs = Subject.objects.filter(code=subject_code, semester=semester)
            if subject_program_code:
                subject_qs = subject_qs.filter(program__code=subject_program_code)
            subject = _resolve_unique(
                subject_qs,
                f'subject with code "{subject_code}"',
                'Add a "Subject Program Code" column to disambiguate.',
            )
        except ValueError as exc:
            errors.append(f'Row {idx}: {exc}')
            continue

        # Section names repeat across programs and year levels too.
        try:
            section_qs = Section.objects.filter(name=section_name, semester=semester)
            if section_program_code:
                section_qs = section_qs.filter(program__code=section_program_code)
            section = _resolve_unique(
                section_qs,
                f'section with name "{section_name}"',
                'Add a "Section Program Code" column to disambiguate.',
            )
        except ValueError as exc:
            errors.append(f'Row {idx}: {exc}')
            continue

        # Room names repeat across buildings.
        try:
            room_qs = Room.objects.filter(room_name=room_name)
            if building_code:
                room_qs = room_qs.filter(building__code=building_code)
            room = _resolve_unique(
                room_qs,
                f'room with name "{room_name}"',
                'Add a "Room Building Code" column to disambiguate.',
            )
        except ValueError as exc:
            errors.append(f'Row {idx}: {exc}')
            continue

        if class_type not in ('Lecture', 'Laboratory'):
            errors.append(f'Row {idx}: class_type must be Lecture or Laboratory.')
            continue

        try:
            day_of_week_val = int(day_of_week)
        except ValueError:
            errors.append(f'Row {idx}: day_of_week must be a number (1-7).')
            continue

        # Imported rows go through the same conflict validation as rows added
        # through the UI, so a spreadsheet cannot create double bookings.
        existing = Schedule.objects.filter(
            semester=semester,
            teacher=teacher,
            subject=subject,
            section=section,
            room=room,
            day_of_week=day_of_week_val,
        ).first()
        conflict = _check_schedule_conflicts(
            semester, teacher, subject, section, room,
            class_type, day_of_week_val, start, end,
            exclude_id=existing.id if existing else None,
        )
        if conflict:
            errors.append(f'Row {idx}: {conflict["conflicts"][0]["message"]}')
            continue

        try:
            schedule, created_flag = Schedule.objects.update_or_create(
                semester=semester,
                teacher=teacher,
                subject=subject,
                section=section,
                room=room,
                day_of_week=day_of_week_val,
                defaults={
                    'class_type': class_type,
                    'start_time': start,
                    'end_time': end,
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
