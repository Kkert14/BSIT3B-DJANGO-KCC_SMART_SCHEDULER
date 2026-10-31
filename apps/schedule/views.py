import json
from datetime import datetime
from urllib.parse import urlencode

import math

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.curriculum.models import Semester
from apps.faculty.models import Faculty
from apps.subject.models import Subject
from apps.section.models import Section
from apps.rooms.models import Room
from apps.building.models import Building
from apps.program.models import Program
from apps.users.decorators import (
    admin_required_api,
    get_user_role,
    teacher_required,
    ROLE_ADMIN,
    ROLE_TEACHER,
)

GRID_START_MINUTES = 7 * 60
GRID_END_MINUTES = 21 * 60
from .models import Schedule


def _active_semester():
    """The term selected in the navbar; schedules always live in it."""
    return (
        Semester.objects.select_related('curriculum')
        .filter(is_active=True, curriculum__is_active=True)
        .first()
    )


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

YEAR_LEVEL_LABELS = {
    1: '1st year',
    2: '2nd year',
    3: '3rd year',
    4: '4th year',
    5: '5th year',
    6: '6th year',
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

    # Faculty double-booking (identical or overlapping slot)
    teacher_clashes = base_qs.filter(teacher=teacher).filter(
        Q(start_time__lt=end_time) & Q(end_time__gt=start_time)
    )
    if teacher_clashes.exists():
        for clash in teacher_clashes:
            conflicts.append({
                'type': 'teacher',
                'message': (
                    f'Faculty "{clash.teacher.first_name} {clash.teacher.last_name}" '
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
            (
                f'{minutes // 60:02d}:{minutes % 60:02d}',
                f'{(minutes + 60) // 60:02d}:{(minutes + 60) % 60:02d}',
            )
            for minutes in range(GRID_START_MINUTES, GRID_END_MINUTES, 60)
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

    limit = subject.lab_hours if class_type == 'Laboratory' else subject.lecture_hours
    if total_hours > limit:
        return {
            'conflicts': [{
                'type': 'time_limit',
                'message': (
                    f'Total {class_type.lower()} time ({total_hours:.1f}h) would exceed the '
                    f'allowed {limit}h for course "{subject}" in section "{section}".'
                ),
            }],
            'suggestions': suggestions,
            'status': 400,
        }

    return None


def _parse_schedule_target(request):
    """Resolve the fields every slot in a schedule plan shares.

    Returns ``(values, error)``. ``values`` maps the target names to their
    model instances and is ``None`` when ``error`` is set.
    """
    teacher_id = request.POST.get('teacher', '').strip()
    subject_id = request.POST.get('subject', '').strip()
    section_id = request.POST.get('section', '').strip()
    room_id = request.POST.get('room', '').strip()
    class_type = request.POST.get('class_type', '').strip()

    semester = _active_semester()
    if semester is None:
        return None, 'Select a curriculum year and semester in the top bar first.'

    try:
        teacher = Faculty.objects.get(pk=int(teacher_id))
    except (Faculty.DoesNotExist, ValueError, TypeError):
        return None, 'Invalid teacher.'
    try:
        subject = Subject.objects.get(pk=int(subject_id))
    except (Subject.DoesNotExist, ValueError, TypeError):
        return None, 'Invalid subject.'
    if subject.semester_id != semester.id:
        return None, 'That course is not offered in the active term.'
    try:
        section = Section.objects.get(pk=int(section_id))
    except (Section.DoesNotExist, ValueError, TypeError):
        return None, 'Invalid section.'
    if section.semester_id != semester.id:
        return None, 'That section is not in the active term.'
    try:
        room = Room.objects.get(pk=int(room_id))
    except (Room.DoesNotExist, ValueError, TypeError):
        return None, 'Invalid room.'

    if class_type not in ('Lecture', 'Laboratory'):
        return None, 'Class type must be Lecture or Laboratory.'

    return {
        'semester': semester,
        'teacher': teacher,
        'subject': subject,
        'section': section,
        'room': room,
        'class_type': class_type,
    }, None


def _parse_schedule_slots(rows):
    """Validate raw plan rows and merge them into ``(slots, error)``.

    Each slot is ``{'row', 'day', 'start', 'end'}`` where ``row`` is the
    1-based position shown to the client.
    """
    if not isinstance(rows, list) or not rows:
        return None, 'Add at least one time slot to the plan.'

    slots = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            return None, f'Row {index}: invalid time slot.'
        raw_day = str(row.get('day', '')).strip()
        try:
            day_of_week = int(raw_day)
        except (ValueError, TypeError):
            return None, f'Row {index}: day of week is required.'
        if day_of_week not in DAY_NAMES:
            return None, f'Row {index}: day of week must be between 1 and 7.'
        start = _parse_time(str(row.get('start', '')).strip())
        end = _parse_time(str(row.get('end', '')).strip())
        if not start:
            return None, f'Row {index}: start time is required.'
        if not end:
            return None, f'Row {index}: end time is required.'
        if end <= start:
            return None, f'Row {index}: end time must be later than start time.'
        for other in slots:
            if (other['day'] == day_of_week and start < other['end']
                    and other['start'] < end):
                return None, (
                    f'Row {index}: overlaps row {other["row"]} on '
                    f'{DAY_NAMES[day_of_week]}.'
                )
        slots.append({
            'row': index,
            'day': day_of_week,
            'start': start,
            'end': end,
        })
    return slots, None


@login_required(login_url='login')
def schedule_list_page(request):
    active_semester = _active_semester()

    filter_program = request.GET.get('program', '').strip()
    if filter_program and not filter_program.isdigit():
        filter_program = ''

    filter_year_level = request.GET.get('year_level', '').strip()
    if filter_year_level and not filter_year_level.isdigit():
        filter_year_level = ''
    filter_section = request.GET.get('section', '').strip()
    query = request.GET.get('q', '').strip()

    term_sections = Section.objects.filter(is_active=True)
    if active_semester:
        term_sections = term_sections.filter(semester=active_semester)
    else:
        term_sections = term_sections.none()

    year_level_scope = term_sections
    if filter_program:
        year_level_scope = year_level_scope.filter(program_id=filter_program)
    year_level_values = list(
        year_level_scope.values_list('year_level', flat=True).distinct().order_by('year_level')
    )
    if filter_year_level and filter_year_level not in {str(level) for level in year_level_values}:
        filter_year_level = ''

    section_choices = term_sections.select_related('program')
    if filter_program:
        section_choices = section_choices.filter(program_id=filter_program)
    if filter_year_level:
        section_choices = section_choices.filter(year_level=filter_year_level)
    section_choices = section_choices.order_by(
        'program__program_code', 'year_level', 'name'
    )
    if filter_section and not section_choices.filter(pk=filter_section).exists():
        filter_section = ''

    schedules_list = Schedule.objects.select_related(
        'teacher', 'subject', 'section__program', 'room__building', 'semester__curriculum'
    ).order_by('day_of_week', 'start_time')
    if active_semester:
        schedules_list = schedules_list.filter(semester=active_semester)
    else:
        schedules_list = schedules_list.none()

    if filter_program:
        schedules_list = schedules_list.filter(section__program_id=filter_program)
    if filter_year_level:
        schedules_list = schedules_list.filter(section__year_level=filter_year_level)
    if filter_section:
        schedules_list = schedules_list.filter(section=filter_section)
    if query:
        schedules_list = schedules_list.filter(
            Q(subject__code__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(section__name__icontains=query) |
            Q(teacher__first_name__icontains=query) |
            Q(teacher__last_name__icontains=query) |
            Q(room__room_name__icontains=query)
        )

    year_level_choices = [
        (level, YEAR_LEVEL_LABELS.get(level, f'{level}th year'))
        for level in year_level_values
    ]

    time_slots = [
        (f'{minutes // 60:02d}:{minutes % 60:02d}', f'{(minutes + 30) // 60:02d}:{(minutes + 30) % 60:02d}')
        for minutes in range(GRID_START_MINUTES, GRID_END_MINUTES, 30)
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

    grid_schedules = list(schedules_list)
    slot_cells = [[None for _ in DAYS] for _ in time_slots]
    for sched in grid_schedules:
        start_index = (sched.start_time.hour * 60 + sched.start_time.minute - GRID_START_MINUTES) // 30
        if start_index < 0 or start_index >= len(time_slots):
            continue
        end_index = math.ceil(
            (sched.end_time.hour * 60 + sched.end_time.minute - GRID_START_MINUTES) / 30
        )
        end_index = min(max(end_index, start_index + 1), len(time_slots))
        column = sched.day_of_week - 1
        if slot_cells[start_index][column] is not None:
            continue
        slot_cells[start_index][column] = {'schedule': sched, 'rowspan': end_index - start_index}
        for row in range(start_index + 1, end_index):
            if slot_cells[row][column] is None:
                slot_cells[row][column] = 'skip'

    timetable_rows = []
    for row_index, (slot_start, slot_end) in enumerate(time_slots):
        cells = []
        for column, (day_num, day_name) in enumerate(DAYS):
            value = slot_cells[row_index][column]
            if value == 'skip':
                cells.append({'kind': 'skip'})
            elif value:
                cells.append({
                    'kind': 'event',
                    'schedule': value['schedule'],
                    'rowspan': value['rowspan'],
                })
            else:
                cells.append({
                    'kind': 'empty',
                    'day': day_num,
                    'day_name': day_name,
                    'start': slot_start,
                    'end': slot_end,
                })
        timetable_rows.append({
            'start': slot_start,
            'end': slot_end,
            'major': row_index % 2 == 0,
            'cells': cells,
        })

    teachers = Faculty.objects.filter(is_active=True).order_by('last_name', 'first_name')
    subjects = Subject.objects.select_related('program').order_by('code')
    sections = term_sections.select_related('program').order_by('name')
    if active_semester:
        subjects = subjects.filter(semester=active_semester)
    else:
        subjects = subjects.none()
    rooms = Room.objects.filter(is_active=True).select_related('building').order_by(
        'building__code', 'room_name'
    )
    buildings = Building.objects.order_by('code')
    programs = Program.objects.filter(
        id__in=term_sections.values('program_id')
    ).order_by('program_code')

    hours_map = {}
    term_schedules = Schedule.objects.all()
    if active_semester:
        term_schedules = term_schedules.filter(semester=active_semester)
    else:
        term_schedules = term_schedules.none()
    for entry in term_schedules.values(
        'semester_id', 'subject_id', 'section_id', 'class_type', 'start_time', 'end_time'
    ):
        key = f"{entry['semester_id']}|{entry['subject_id']}|{entry['section_id']}|{entry['class_type']}"
        hours_map[key] = round(
            hours_map.get(key, 0) + _time_duration_hours(entry['start_time'], entry['end_time']), 2
        )

    lecture_hours = sum(
        _time_duration_hours(s.start_time, s.end_time)
        for s in grid_schedules if s.class_type == 'Lecture'
    )
    lab_hours = sum(
        _time_duration_hours(s.start_time, s.end_time)
        for s in grid_schedules if s.class_type == 'Laboratory'
    )
    stats = [
        {
            'label': 'Classes',
            'icon': 'fa-regular fa-calendar-days',
            'value': str(len(grid_schedules)),
            'note': 'In the active term' if active_semester else 'No active term',
        },
        {
            'label': 'Lecture hours',
            'icon': 'fa-solid fa-chalkboard',
            'value': f'{lecture_hours:.0f}h',
            'note': 'Weekly lecture load',
        },
        {
            'label': 'Laboratory hours',
            'icon': 'fa-solid fa-flask',
            'value': f'{lab_hours:.0f}h',
            'note': 'Weekly laboratory load',
        },
        {
            'label': 'Sections covered',
            'icon': 'fa-solid fa-layer-group',
            'value': str(len({s.section_id for s in grid_schedules})),
            'note': 'Sections with at least one class',
        },
    ]

    return render(request, 'schedule_list.html', {
        'timetable_rows': timetable_rows,
        'DAYS': DAYS,
        'all_schedules': schedules_list,
        'query': query,
        'teachers': teachers,
        'subjects': subjects,
        'sections': sections,
        'section_choices': section_choices,
        'rooms': rooms,
        'buildings': buildings,
        'programs': programs,
        'stats': stats,
        'hours_map': hours_map,
        'filter_program': filter_program,
        'filter_year_level': filter_year_level,
        'filter_section': filter_section,
        'year_level_choices': year_level_choices,
        'active_semester': active_semester,
        'has_grid_events': any(value not in (None, 'skip') for row in slot_cells for value in row),
    })


@admin_required_api
@login_required(login_url='login')
def schedule_faculty_load_ajax(request):
    """Return weekly load per faculty for the active term, plus one faculty's blocks."""
    semester = _active_semester()
    teacher_id = request.GET.get('teacher', '').strip()
    if semester is None:
        return JsonResponse({'teachers': {}, 'blocks': []})

    schedule_qs = Schedule.objects.filter(semester=semester)
    teachers = {}
    for entry in schedule_qs.values('teacher_id', 'start_time', 'end_time'):
        item = teachers.setdefault(entry['teacher_id'], {'hours': 0.0, 'count': 0})
        item['hours'] += _time_duration_hours(entry['start_time'], entry['end_time'])
        item['count'] += 1
    for item in teachers.values():
        item['hours'] = round(item['hours'], 2)

    payload = {'teachers': teachers, 'blocks': []}
    if teacher_id.isdigit():
        blocks = (
            schedule_qs.filter(teacher_id=teacher_id)
            .select_related('subject', 'section', 'room__building')
            .order_by('day_of_week', 'start_time')
        )
        payload['teacher_id'] = teacher_id
        payload['blocks'] = [
            {
                'day': block.day_of_week,
                'start': block.start_time.strftime('%H:%M'),
                'end': block.end_time.strftime('%H:%M'),
                'subject': block.subject.code,
                'section': block.section.name,
                'room': f'{block.room.building.code} {block.room.room_name}',
                'class_type': block.class_type,
            }
            for block in blocks
        ]
    return JsonResponse(payload)


@login_required(login_url='login')
def schedule_list_ajax(request):
    query = request.GET.get('q', '').strip()
    semester = _active_semester()
    schedules_list = Schedule.objects.select_related(
        'teacher', 'subject', 'section', 'room', 'semester__curriculum'
    )
    if semester:
        schedules_list = schedules_list.filter(semester=semester)
    else:
        schedules_list = schedules_list.none()
    if query:
        schedules_list = schedules_list.filter(
            Q(subject__code__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(section__name__icontains=query) |
            Q(teacher__first_name__icontains=query) |
            Q(teacher__last_name__icontains=query) |
            Q(room__room_name__icontains=query)
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
        teacher = Faculty.objects.filter(pk=tid).first()
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

    target, error = _parse_schedule_target(request)
    if error:
        return JsonResponse({'error': error}, status=400)
    semester = target['semester']
    teacher = target['teacher']
    subject = target['subject']
    section = target['section']
    room = target['room']
    class_type = target['class_type']

    day_of_week = request.POST.get('day_of_week', '').strip()
    start_time = _parse_time(request.POST.get('start_time', ''))
    end_time = _parse_time(request.POST.get('end_time', ''))

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
def schedule_batch_save_ajax(request):
    """Create or extend a batch of slots that share one subject/section/room.

    The inline editor sends the plan rows as JSON; the first row updates the
    edited schedule (when an ``id`` is supplied) and the rest are created in a
    single transaction so a partly-valid plan never lands in the database.
    """
    target, error = _parse_schedule_target(request)
    if error:
        return JsonResponse({'error': error}, status=400)

    schedule = None
    schedule_id = request.POST.get('id', '').strip()
    if schedule_id:
        schedule = get_object_or_404(Schedule, pk=schedule_id)

    try:
        rows = json.loads(request.POST.get('rows') or '[]')
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Schedule plan is not valid.'}, status=400)

    slots, error = _parse_schedule_slots(rows)
    if error:
        return JsonResponse({'error': error}, status=400)

    semester = target['semester']
    teacher = target['teacher']
    subject = target['subject']
    section = target['section']
    room = target['room']
    class_type = target['class_type']

    # Aggregate hours cover the whole plan at once, so the per-row conflict
    # check below never has to guess about rows that are not saved yet.
    existing_same = Schedule.objects.filter(
        semester=semester,
        subject=subject,
        section=section,
        class_type=class_type,
    )
    if schedule is not None:
        existing_same = existing_same.exclude(pk=schedule.pk)
    scheduled_hours = sum(
        _time_duration_hours(entry.start_time, entry.end_time)
        for entry in existing_same
    )
    planned_hours = sum(_time_duration_hours(slot['start'], slot['end']) for slot in slots)
    total_hours = scheduled_hours + planned_hours
    limit = subject.lab_hours if class_type == 'Laboratory' else subject.lecture_hours
    if total_hours > limit:
        return JsonResponse({
            'batch': True,
            'conflicts': [{
                'type': 'time_limit',
                'message': (
                    f'This plan adds {planned_hours:.1f}h on top of the '
                    f'{scheduled_hours:.1f}h already scheduled ({total_hours:.1f}h total). '
                    f'The allowed {class_type.lower()} time for course "{subject}" '
                    f'in section "{section}" is {limit}h.'
                ),
            }],
            'suggestions': {},
        }, status=400)

    conflicts = []
    suggestions = {}
    exclude_id = schedule.pk if schedule is not None else None
    for slot in slots:
        conflict = _check_schedule_conflicts(
            semester, teacher, subject, section, room,
            class_type, slot['day'], slot['start'], slot['end'],
            exclude_id=exclude_id,
        )
        if not conflict:
            continue
        for item in conflict['conflicts']:
            item = dict(item)
            item['message'] = f'Row {slot["row"]}: {item["message"]}'
            conflicts.append(item)
        if not suggestions:
            suggestions = conflict['suggestions']

    if conflicts:
        return JsonResponse({
            'batch': True,
            'conflicts': conflicts,
            'suggestions': suggestions,
        }, status=400)

    created = 0
    updated = 0
    try:
        with transaction.atomic():
            for index, slot in enumerate(slots):
                if index == 0 and schedule is not None:
                    entry = schedule
                    updated += 1
                else:
                    entry = Schedule()
                    created += 1
                entry.semester = semester
                entry.teacher = teacher
                entry.subject = subject
                entry.section = section
                entry.room = room
                entry.class_type = class_type
                entry.day_of_week = slot['day']
                entry.start_time = slot['start']
                entry.end_time = slot['end']
                entry.save()
    except IntegrityError:
        return JsonResponse({'error': 'Could not save the schedule plan due to a conflict.'}, status=400)

    teacher_hours = sum(
        _time_duration_hours(entry.start_time, entry.end_time)
        for entry in Schedule.objects.filter(semester=semester, teacher=teacher)
    )
    messages.success(
        request,
        f'Schedule plan saved ({created + updated} slot(s)) — '
        f'{teacher.first_name} {teacher.last_name} now has '
        f'{teacher_hours:.1f}h this semester.',
    )
    return JsonResponse({
        'status': 'success',
        'created': created,
        'updated': updated,
        'count': created + updated,
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


# ---------------------------------------------------------------- reports
REPORT_TYPES = (
    ('master', 'Master list'),
    ('timetable', 'Section timetable'),
    ('faculty', 'Faculty schedule'),
)
REPORT_LABELS = dict(REPORT_TYPES)
REPORT_HEADERS = [
    'Day', 'Start', 'End', 'Hours', 'Course code', 'Course title',
    'Type', 'Program', 'Year', 'Section', 'Faculty', 'Room',
]


def _report_clock(minutes, mode):
    """Format a minute offset from midnight as 24-hour or 12-hour text."""
    hours, mins = divmod(int(minutes) % (24 * 60), 60)
    if mode != 'standard':
        return f'{hours:02d}:{mins:02d}'
    suffix = 'AM' if hours < 12 else 'PM'
    return f'{hours % 12 or 12}:{mins:02d} {suffix}'


def _report_time(value, mode):
    return _report_clock(value.hour * 60 + value.minute, mode)


def _report_hours(value):
    """Trim trailing zeros from an hours figure (1.5 -> '1.5', 2.0 -> '2')."""
    return f'{value:.2f}'.rstrip('0').rstrip('.')


def _report_rows(schedules, mode):
    rows = []
    for sched in schedules:
        hours = _time_duration_hours(sched.start_time, sched.end_time)
        rows.append({
            'day': DAY_NAMES.get(sched.day_of_week, str(sched.day_of_week)),
            'day_num': sched.day_of_week,
            'start': _report_time(sched.start_time, mode),
            'end': _report_time(sched.end_time, mode),
            'hours': hours,
            'hours_display': _report_hours(hours),
            'subject_id': sched.subject_id,
            'subject_code': sched.subject.code,
            'subject_name': sched.subject.name,
            'class_type': sched.class_type,
            'is_lab': sched.class_type == 'Laboratory',
            'program': sched.section.program.program_code,
            'year_level': YEAR_LEVEL_LABELS.get(
                sched.section.year_level, f'{sched.section.year_level}th year'
            ),
            'section': sched.section.name,
            'teacher': sched.teacher.full_name,
            'employee_number': sched.teacher.employee_number,
            'room': f'{sched.room.building.code} {sched.room.room_name}',
        })
    return rows


def _report_totals(rows):
    lecture = sum(row['hours'] for row in rows if not row['is_lab'])
    lab = sum(row['hours'] for row in rows if row['is_lab'])
    return {
        'blocks': len(rows),
        'courses': len({row['subject_id'] for row in rows}),
        'lecture_hours': lecture,
        'lab_hours': lab,
        'total_hours': lecture + lab,
        'lecture_display': _report_hours(lecture),
        'lab_display': _report_hours(lab),
        'total_display': _report_hours(lecture + lab),
    }


def _report_grid(schedules, mode):
    """Build a day-by-time grid for a single section or faculty member."""
    if not schedules:
        return {'days': [], 'rows': [], 'has_events': False}

    starts = [s.start_time.hour * 60 + s.start_time.minute for s in schedules]
    ends = [s.end_time.hour * 60 + s.end_time.minute for s in schedules]
    start_minutes = min(7 * 60, (min(starts) // 30) * 30)
    end_minutes = max(17 * 60, math.ceil(max(ends) / 30) * 30)

    used_days = {s.day_of_week for s in schedules}
    days = [(number, DAY_NAMES[number]) for number in range(1, 6)]
    days += [(number, DAY_NAMES[number]) for number in (6, 7) if number in used_days]

    slot_starts = list(range(start_minutes, end_minutes, 30))
    slot_index = {value: index for index, value in enumerate(slot_starts)}
    cells = [[None for _ in days] for _ in slot_starts]

    for sched in schedules:
        start_at = slot_index.get(
            (sched.start_time.hour * 60 + sched.start_time.minute) // 30 * 30
        )
        if start_at is None:
            continue
        raw_end = math.ceil(
            (sched.end_time.hour * 60 + sched.end_time.minute) / 30
        ) * 30
        end_at = min(
            max(slot_index.get(raw_end, len(slot_starts)), start_at + 1),
            len(slot_starts),
        )
        column = next(
            (index for index, (number, _) in enumerate(days)
             if number == sched.day_of_week),
            None,
        )
        if column is None or cells[start_at][column] is not None:
            continue
        cells[start_at][column] = {'schedule': sched, 'rowspan': end_at - start_at}
        for row in range(start_at + 1, end_at):
            if cells[row][column] is None:
                cells[row][column] = 'skip'

    rows = []
    for index, minutes in enumerate(slot_starts):
        cells_out = []
        for value in cells[index]:
            if value == 'skip':
                cells_out.append({'kind': 'skip'})
            elif value:
                cells_out.append({
                    'kind': 'event',
                    'schedule': value['schedule'],
                    'rowspan': value['rowspan'],
                })
            else:
                cells_out.append({'kind': 'empty'})
        rows.append({
            'start': _report_clock(minutes, mode),
            'end': _report_clock(minutes + 30, mode),
            'major': index % 2 == 0,
            'cells': cells_out,
        })

    return {'days': days, 'rows': rows, 'has_events': True}


def _build_report_context(request):
    """Return ``(context, None)`` or ``(None, redirect)`` for report pages."""
    role = get_user_role(request.user)
    teacher_profile = None
    if role == ROLE_TEACHER:
        teacher_profile = Faculty.objects.filter(user=request.user).first()
        if teacher_profile is None:
            messages.error(
                request,
                'Your account is not linked to a faculty record yet. '
                'Ask an administrator to link it before viewing reports.',
            )
            return None, redirect('schedule:schedule_list')

    report = request.GET.get('report', '').strip()
    if teacher_profile is not None:
        report = 'faculty'
    if report not in REPORT_LABELS:
        report = 'master'

    active_semester = _active_semester()

    filter_program = request.GET.get('program', '').strip()
    if filter_program and not filter_program.isdigit():
        filter_program = ''
    filter_year_level = request.GET.get('year_level', '').strip()
    if filter_year_level and not filter_year_level.isdigit():
        filter_year_level = ''
    filter_section = request.GET.get('section', '').strip()
    if filter_section and not filter_section.isdigit():
        filter_section = ''

    term_sections = Section.objects.filter(is_active=True)
    if active_semester:
        term_sections = term_sections.filter(semester=active_semester)
    else:
        term_sections = term_sections.none()

    year_level_scope = term_sections
    if filter_program:
        year_level_scope = year_level_scope.filter(program_id=filter_program)
    year_level_values = list(
        year_level_scope.values_list('year_level', flat=True).distinct().order_by('year_level')
    )
    if filter_year_level and filter_year_level not in {str(level) for level in year_level_values}:
        filter_year_level = ''

    section_choices = term_sections.select_related('program')
    if filter_program:
        section_choices = section_choices.filter(program_id=filter_program)
    if filter_year_level:
        section_choices = section_choices.filter(year_level=filter_year_level)
    section_choices = section_choices.order_by(
        'program__program_code', 'year_level', 'name'
    )

    if report == 'timetable':
        if filter_section and not section_choices.filter(pk=filter_section).exists():
            filter_section = ''
        if not filter_section and section_choices:
            filter_section = str(section_choices[0].id)
    else:
        filter_section = ''

    teachers = Faculty.objects.filter(is_active=True).order_by('last_name', 'first_name')
    filter_teacher = ''
    if teacher_profile is not None:
        filter_teacher = str(teacher_profile.id)
    elif report == 'faculty':
        filter_teacher = request.GET.get('teacher', '').strip()
        if filter_teacher and not filter_teacher.isdigit():
            filter_teacher = ''
        if filter_teacher and not teachers.filter(pk=filter_teacher).exists():
            filter_teacher = ''

    selected_teacher = (
        teachers.filter(pk=filter_teacher).first() if filter_teacher else None
    )
    if report == 'faculty' and teacher_profile is not None:
        selected_teacher = teacher_profile

    view = request.GET.get('view', '').strip()
    if report == 'master':
        view = 'table'
    if view not in ('table', 'grid'):
        view = 'table'

    time_mode = (
        'standard' if request.COOKIES.get('time_format') == 'standard' else 'military'
    )

    schedules = (
        Schedule.objects.select_related(
            'teacher', 'subject', 'section__program', 'room__building',
            'semester__curriculum',
        )
        .order_by('day_of_week', 'start_time', 'section__program__program_code',
                  'section__name')
    )
    if active_semester:
        schedules = schedules.filter(semester=active_semester)
    else:
        schedules = schedules.none()
    if filter_program:
        schedules = schedules.filter(section__program_id=filter_program)
    if filter_year_level:
        schedules = schedules.filter(section__year_level=filter_year_level)
    if filter_section:
        schedules = schedules.filter(section_id=filter_section)
    if teacher_profile is not None:
        schedules = schedules.filter(teacher_id=teacher_profile.id)
    base_schedules = list(schedules)
    if filter_teacher and teacher_profile is None:
        schedules = [
            sched for sched in base_schedules
            if sched.teacher_id == int(filter_teacher)
        ]
    else:
        schedules = base_schedules

    programs = Program.objects.filter(
        id__in=term_sections.values('program_id')
    ).order_by('program_code')

    if active_semester:
        term_label = (
            f'A.Y. {active_semester.curriculum.academic_year} '
            f'· {active_semester.short_label}'
        )
    else:
        term_label = 'No active term'

    if report == 'timetable':
        selected_section = section_choices.filter(pk=filter_section).first()
        if selected_section is not None:
            scope_label = ' · '.join(part for part in (
                selected_section.program.program_code,
                selected_section.name,
                YEAR_LEVEL_LABELS.get(selected_section.year_level, ''),
            ) if part)
        else:
            scope_label = 'Select a section'
    elif report == 'faculty':
        if selected_teacher is not None:
            scope_label = (
                f'{selected_teacher.full_name} · {selected_teacher.employee_number}'
            )
        else:
            scope_label = 'All faculty'
    else:
        scope_parts = []
        if filter_program:
            program_obj = programs.filter(pk=filter_program).first()
            scope_parts.append(
                program_obj.program_code if program_obj else 'Selected program'
            )
        else:
            scope_parts.append('All programs')
        if filter_year_level:
            scope_parts.append(
                YEAR_LEVEL_LABELS.get(
                    int(filter_year_level), f'{filter_year_level}th year'
                )
            )
        scope_label = ' · '.join(scope_parts)

    report_title = REPORT_LABELS[report]

    show_load_summary = (
        report == 'faculty' and selected_teacher is None and active_semester is not None
    )
    sheets = []
    load_rows = []
    load_totals = None
    teacher_cards = []

    if report == 'faculty' and teacher_profile is None:
        grouped = {}
        for sched in base_schedules:
            grouped.setdefault(sched.teacher_id, []).append(sched)
        scheduled_rows = []
        for teacher in teachers:
            rows = _report_rows(grouped.get(teacher.id, []), time_mode)
            totals = _report_totals(rows)
            scheduled_rows.extend(rows)
            teacher_cards.append({
                'id': teacher.id,
                'name': teacher.full_name,
                'employee_number': teacher.employee_number,
                'position': teacher.position,
                'initials': (
                    f'{teacher.first_name[:1]}{teacher.last_name[:1]}'.upper()
                ),
                'search': ' '.join(filter(None, (
                    teacher.full_name, teacher.employee_number, teacher.position,
                ))).lower(),
                'blocks': totals['blocks'],
                'courses': totals['courses'],
                'total_display': totals['total_display'],
                'lecture_display': totals['lecture_display'],
                'lab_display': totals['lab_display'],
                'total_hours': totals['total_hours'],
            })
        load_rows = list(teacher_cards)
        load_totals = _report_totals(scheduled_rows)
        load_totals['blocks'] = sum(row['blocks'] for row in load_rows)
        load_totals['courses'] = sum(row['courses'] for row in load_rows)

    if not show_load_summary:
        rows = _report_rows(schedules, time_mode)
        totals = _report_totals(rows)
        sheets.append({
            'title': selected_teacher.full_name if selected_teacher else report_title,
            'scope': (
                f'{selected_teacher.employee_number} · {report_title}'
                if selected_teacher else scope_label
            ),
            'rows': rows,
            'grid': _report_grid(schedules, time_mode),
            'totals': totals,
            'show_teacher': report != 'faculty',
        })

    if show_load_summary:
        export_schedules = sorted(
            schedules,
            key=lambda s: (
                s.teacher.last_name.lower(), s.teacher.first_name.lower(),
                s.day_of_week, s.start_time,
            ),
        )
    else:
        export_schedules = schedules
    export_rows = _report_rows(export_schedules, time_mode)

    params = {
        'report': report,
        'program': filter_program,
        'year_level': filter_year_level,
        'section': filter_section,
        'teacher': filter_teacher,
        'view': view,
    }

    report_tabs = []
    if role == ROLE_ADMIN:
        for value, label in REPORT_TYPES:
            tab_params = {'report': value}
            if value in ('master', 'timetable'):
                if filter_program:
                    tab_params['program'] = filter_program
                if filter_year_level:
                    tab_params['year_level'] = filter_year_level
            if value == 'timetable' and filter_section:
                tab_params['section'] = filter_section
            if value == 'faculty' and filter_teacher:
                tab_params['teacher'] = filter_teacher
            report_tabs.append({
                'value': value,
                'label': label,
                'query': urlencode({
                    key: val for key, val in tab_params.items() if val
                }),
            })
    faculty_base_query = urlencode({'report': 'faculty'})

    return {
        'report': report,
        'report_label': report_title,
        'report_types': REPORT_TYPES if role == ROLE_ADMIN else (REPORT_TYPES[2],),
        'report_tabs': report_tabs,
        'faculty_base_query': faculty_base_query,
        'view': view,
        'can_choose_view': report != 'master',
        'active_semester': active_semester,
        'filter_program': filter_program,
        'filter_year_level': filter_year_level,
        'filter_section': filter_section,
        'filter_teacher': filter_teacher,
        'programs': programs,
        'section_choices': section_choices,
        'year_level_choices': [
            (level, YEAR_LEVEL_LABELS.get(level, f'{level}th year'))
            for level in year_level_values
        ],
        'teachers': teachers,
        'teacher_cards': teacher_cards,
        'selected_teacher': selected_teacher,
        'is_teacher_view': teacher_profile is not None,
        'sheets': sheets,
        'sheet_count': len(sheets),
        'show_load_summary': show_load_summary,
        'load_rows': load_rows,
        'load_totals': load_totals,
        'export_rows': export_rows,
        'has_any': bool(schedules),
        'report_title': report_title,
        'scope_label': scope_label,
        'term_label': term_label,
        'generated_at': timezone.localtime(),
        'query_string': urlencode({key: value for key, value in params.items() if value}),
        'time_format': time_mode,
    }, None


@teacher_required
def schedule_reports(request):
    context, redirect_response = _build_report_context(request)
    if redirect_response is not None:
        return redirect_response
    return render(request, 'schedule_reports.html', context)


@teacher_required
def schedule_reports_export(request):
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    context, redirect_response = _build_report_context(request)
    if redirect_response is not None:
        return redirect_response

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = context['report_label'][:31]

    last_column = len(REPORT_HEADERS)
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_column)
    title_cell = sheet.cell(row=1, column=1, value=f"Smart Scheduler — {context['report_label']}")
    title_cell.font = Font(bold=True, size=14)
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_column)
    sheet.cell(
        row=2, column=1,
        value=f"Term: {context['term_label']}    Scope: {context['scope_label']}",
    )
    sheet.merge_cells(start_row=3, start_column=1, end_row=3, end_column=last_column)
    sheet.cell(
        row=3, column=1,
        value=f"Generated: {context['generated_at'].strftime('%b %d, %Y %H:%M')}",
    )

    header_row = 5
    header_fill = PatternFill('solid', fgColor='EEF2FB')
    for column, label in enumerate(REPORT_HEADERS, start=1):
        cell = sheet.cell(row=header_row, column=column, value=label)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')

    teacher_column = REPORT_HEADERS.index('Faculty')
    row_index = header_row + 1
    for row in context['export_rows']:
        values = [
            row['day'], row['start'], row['end'], row['hours'],
            row['subject_code'], row['subject_name'], row['class_type'],
            row['program'], row['year_level'], row['section'],
            row['teacher'], row['room'],
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=row_index, column=column, value=value)
            if column == 4:
                cell.number_format = '0.0'
        sheet.cell(row=row_index, column=teacher_column).font = Font(bold=True)
        row_index += 1

    total_row = row_index
    sheet.cell(row=total_row, column=1, value='TOTAL').font = Font(bold=True)
    total_hours = sum(row['hours'] for row in context['export_rows'])
    hours_cell = sheet.cell(row=total_row, column=4, value=total_hours)
    hours_cell.number_format = '0.0'
    hours_cell.font = Font(bold=True)
    sheet.cell(row=total_row, column=2, value=f"{len(context['export_rows'])} block(s)")

    widths = [12, 10, 10, 8, 14, 34, 12, 12, 10, 18, 24, 18]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)

    if context['show_load_summary']:
        load_sheet = workbook.create_sheet('Faculty load')
        load_headers = [
            'Faculty', 'Employee no.', 'Position', 'Blocks', 'Courses',
            'Lecture hours', 'Lab hours', 'Total hours',
        ]
        for column, label in enumerate(load_headers, start=1):
            cell = load_sheet.cell(row=1, column=column, value=label)
            cell.font = Font(bold=True)
            cell.fill = header_fill
        load_row_index = 2
        for row in context['load_rows']:
            for column, value in enumerate([
                row['name'], row['employee_number'], row['position'],
                row['blocks'], row['courses'], row['lecture_hours'],
                row['lab_hours'], row['total_hours'],
            ], start=1):
                cell = load_sheet.cell(row=load_row_index, column=column, value=value)
                if column >= 6:
                    cell.number_format = '0.0'
            load_row_index += 1
        totals = context['load_totals']
        for column, value in enumerate([
            'TOTAL', '', '', totals['blocks'], totals['courses'],
            totals['lecture_hours'], totals['lab_hours'], totals['total_hours'],
        ], start=1):
            cell = load_sheet.cell(row=load_row_index, column=column, value=value)
            cell.font = Font(bold=True)
            if column >= 6:
                cell.number_format = '0.0'
        widths = [26, 16, 22, 9, 9, 14, 11, 12]
        for index, width in enumerate(widths, start=1):
            load_sheet.column_dimensions[get_column_letter(index)].width = width

    stream = BytesIO()
    workbook.save(stream)
    response = HttpResponse(
        stream.getvalue(),
        content_type=(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ),
    )
    filename = f'schedule_report_{context["report"]}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


