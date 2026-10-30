import json
from datetime import datetime, timedelta

import math

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError, transaction

from apps.curriculum.models import Curriculum, Semester
from apps.faculty.models import Faculty
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

    limit = (
        subject.total_hours
        if (class_type == 'Laboratory') == subject.is_lab
        else 0
    )
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


def _parse_schedule_target(request):
    """Resolve the fields every slot in a schedule plan shares.

    Returns ``(values, error)``. ``values`` maps the target names to their
    model instances and is ``None`` when ``error`` is set.
    """
    semester_id = request.POST.get('semester', '').strip()
    teacher_id = request.POST.get('teacher', '').strip()
    subject_id = request.POST.get('subject', '').strip()
    section_id = request.POST.get('section', '').strip()
    room_id = request.POST.get('room', '').strip()
    class_type = request.POST.get('class_type', '').strip()

    if not semester_id:
        return None, 'Semester is required.'
    try:
        semester = Semester.objects.get(pk=int(semester_id))
    except (Semester.DoesNotExist, ValueError, TypeError):
        return None, 'Invalid semester.'

    try:
        teacher = Faculty.objects.get(pk=int(teacher_id))
    except (Faculty.DoesNotExist, ValueError, TypeError):
        return None, 'Invalid teacher.'
    try:
        subject = Subject.objects.get(pk=int(subject_id))
    except (Subject.DoesNotExist, ValueError, TypeError):
        return None, 'Invalid subject.'
    try:
        section = Section.objects.get(pk=int(section_id))
    except (Section.DoesNotExist, ValueError, TypeError):
        return None, 'Invalid section.'
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
    active_curriculum = Curriculum.objects.filter(is_active=True).first()
    active_semester = (
        Semester.objects.select_related('curriculum')
        .filter(is_active=True, curriculum__is_active=True)
        .first()
    )

    year_param = request.GET.get('year')
    if year_param is None:
        filter_year = str(active_curriculum.id) if active_curriculum else ''
    else:
        filter_year = year_param.strip()
    if filter_year and not filter_year.isdigit():
        filter_year = ''

    semester_param = request.GET.get('semester')
    if semester_param is None:
        filter_semester = str(active_semester.semester_number) if active_semester else ''
    else:
        filter_semester = semester_param.strip()
    if filter_semester not in {'1', '2', '3'}:
        filter_semester = ''

    filter_year_level = request.GET.get('year_level', '').strip()
    if filter_year_level and not filter_year_level.isdigit():
        filter_year_level = ''
    filter_section = request.GET.get('section', '').strip()
    query = request.GET.get('q', '').strip()

    year_level_scope = Section.objects.filter(is_active=True)
    if filter_year:
        year_level_scope = year_level_scope.filter(semester__curriculum_id=filter_year)
    if filter_semester:
        year_level_scope = year_level_scope.filter(semester__semester_number=filter_semester)
    year_level_values = list(
        year_level_scope.values_list('year_level', flat=True).distinct().order_by('year_level')
    )
    if filter_year_level and filter_year_level not in {str(level) for level in year_level_values}:
        filter_year_level = ''

    section_choices = Section.objects.filter(is_active=True).select_related('program')
    if filter_year:
        section_choices = section_choices.filter(semester__curriculum_id=filter_year)
    if filter_semester:
        section_choices = section_choices.filter(semester__semester_number=filter_semester)
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

    if filter_year:
        schedules_list = schedules_list.filter(semester__curriculum_id=filter_year)
    if filter_semester:
        schedules_list = schedules_list.filter(semester__semester_number=filter_semester)
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
            Q(room__room_name__icontains=query) |
            Q(semester__curriculum__academic_year__icontains=query)
        )

    semesters = Semester.objects.select_related('curriculum').order_by(
        'curriculum__academic_year', 'semester_number'
    )

    year_level_choices = [
        (level, YEAR_LEVEL_LABELS.get(level, f'{level}th year'))
        for level in year_level_values
    ]

    editor_semester = None
    if filter_semester:
        editor_scope = Semester.objects.filter(semester_number=filter_semester)
        if filter_year:
            editor_scope = editor_scope.filter(curriculum_id=filter_year)
        elif active_curriculum:
            editor_scope = editor_scope.filter(curriculum=active_curriculum)
        editor_semester = editor_scope.select_related('curriculum').first()
    if editor_semester is None:
        editor_semester = active_semester

    time_slots = [
        (f'{minutes // 60:02d}:{minutes % 60:02d}', f'{(minutes + 30) // 60:02d}:{(minutes + 30) % 60:02d}')
        for minutes in range(7 * 60, 17 * 60, 30)
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
        start_index = (sched.start_time.hour * 60 + sched.start_time.minute - 7 * 60) // 30
        if start_index < 0 or start_index >= len(time_slots):
            continue
        end_index = math.ceil(
            (sched.end_time.hour * 60 + sched.end_time.minute - 7 * 60) / 30
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
    subjects = Subject.objects.select_related('program', 'semester').order_by('code')
    sections = Section.objects.filter(is_active=True).select_related(
        'program', 'semester'
    ).order_by('name')
    rooms = Room.objects.filter(is_active=True).select_related('building').order_by(
        'building__code', 'room_name'
    )
    buildings = Building.objects.order_by('code')
    programs = Program.objects.order_by('program_code')
    curricula = Curriculum.objects.order_by('-academic_year')

    hours_map = {}
    for entry in Schedule.objects.values(
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
            'note': 'In the current filter',
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
        'curricula': curricula,
        'stats': stats,
        'hours_map': hours_map,
        'filter_year': filter_year,
        'filter_semester': filter_semester,
        'filter_year_level': filter_year_level,
        'filter_section': filter_section,
        'semester_filter_choices': Semester.SEMESTER_CHOICES,
        'year_level_choices': year_level_choices,
        'editor_semester_id': editor_semester.id if editor_semester else '',
        'semesters': semesters,
        'active_semester': active_semester,
        'has_grid_events': any(value not in (None, 'skip') for row in slot_cells for value in row),
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
    limit = (
        subject.total_hours
        if (class_type == 'Laboratory') == subject.is_lab
        else 0
    )
    if total_hours > limit:
        return JsonResponse({
            'batch': True,
            'conflicts': [{
                'type': 'time_limit',
                'message': (
                    f'This plan adds {planned_hours:.1f}h on top of the '
                    f'{scheduled_hours:.1f}h already scheduled ({total_hours:.1f}h total). '
                    f'The allowed {class_type.lower()} time for subject "{subject}" '
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

    messages.success(request, f'Schedule plan saved ({created + updated} slot(s)).')
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
            'subject__code', 'subject__program__program_code',
            'section__name', 'section__program__program_code',
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
        subject_program_code = get_str(row, 'subject_program_program_code')
        section_name = get_str(row, 'section__name')
        section_program_code = get_str(row, 'section_program_program_code')
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
            teacher = Faculty.objects.get(employee_number=teacher_emp)
        except Faculty.DoesNotExist:
            errors.append(f'Row {idx}: teacher with employee number "{teacher_emp}" not found.')
            continue

        # Subject codes repeat across programs, so narrow the lookup down with
        # whichever extra columns the spreadsheet provides.
        try:
            subject_qs = Subject.objects.filter(code=subject_code, semester=semester)
            if subject_program_code:
                subject_qs = subject_qs.filter(program__program_code=subject_program_code)
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
                section_qs = section_qs.filter(program__program_code=section_program_code)
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
