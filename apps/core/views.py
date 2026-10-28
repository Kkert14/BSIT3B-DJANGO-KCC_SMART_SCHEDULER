from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

User = get_user_model()

from apps.curriculum.models import Semester
from apps.schedule.models import Schedule
from apps.faculty.models import Faculty
from apps.subject.models import Subject
from apps.section.models import Section
from apps.rooms.models import Room
from apps.users.decorators import ROLE_TEACHER, get_user_role
from apps.users.models import LoginAttempt

MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=1)
INVALID_LOGIN_MESSAGE = 'Invalid username or password.'
LOCKED_MESSAGE = 'Too many failed attempts. Locked for 1 minute.'


def _get_lock_state(username):
    """Return ``(failed_attempts, seconds_remaining)`` for ``username``.

    ``seconds_remaining`` is ``None`` when the account is not locked.
    """
    try:
        attempt = LoginAttempt.objects.get(username=username)
    except LoginAttempt.DoesNotExist:
        return 0, None

    if attempt.locked_until is not None:
        if attempt.is_locked:
            return attempt.failed_count, attempt.seconds_remaining()

        # The lock has expired, so the account is usable again.
        attempt.delete()
        return 0, None

    # Not locked - keep counting the failures that have not added up yet.
    return attempt.failed_count, None


def _register_failure(username):
    """Record a failed sign-in and lock the account when the limit is hit."""
    attempt, _ = LoginAttempt.objects.get_or_create(username=username)
    attempt.failed_count += 1
    if attempt.failed_count >= MAX_FAILED_ATTEMPTS:
        attempt.locked_until = timezone.now() + LOCK_DURATION
    attempt.save()
    return attempt


def _reset_lock_state(username):
    """Clear the failure counter after a successful sign-in."""
    LoginAttempt.objects.filter(username=username).delete()


def _validate_registration_data(data):
    errors = {}

    username = data.get('username', '').strip()
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    if not username:
        errors['username'] = 'Username is required.'
    elif User.objects.filter(username=username).exists():
        errors['username'] = 'Username already taken.'

    if not first_name:
        errors['first_name'] = 'First name is required.'

    if not last_name:
        errors['last_name'] = 'Last name is required.'

    if not email:
        errors['email'] = 'Email is required.'
    else:
        try:
            validate_email(email)
        except ValidationError:
            errors['email'] = 'Enter a valid email address.'
        else:
            if User.objects.filter(email=email).exists():
                errors['email'] = 'Email already registered.'

    if not password:
        errors['password'] = 'Password is required.'
    elif len(password) < 8:
        errors['password'] = 'Password must be at least 8 characters.'
    else:
        try:
            validate_password(password)
        except ValidationError as exc:
            errors['password'] = ' '.join(exc.messages)

    if password != confirm_password:
        errors['confirm_password'] = 'Passwords do not match.'

    return errors


@require_http_methods(['GET', 'POST'])
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'GET':
        return render(request, 'auth/login.html')

    username = request.POST.get('username', '').strip()

    failed_attempts, remaining = _get_lock_state(username)
    if remaining is not None:
        messages.error(request, f'Too many failed attempts. Try again in {remaining} seconds.')
        return render(request, 'auth/login.html', {'locked': True, 'remaining': remaining})

    password = request.POST.get('password', '')
    user = authenticate(request, username=username, password=password)

    if user is not None:
        _reset_lock_state(username)
        login(request, user)
        return redirect('dashboard')

    attempt = _register_failure(username)
    if attempt.failed_count >= MAX_FAILED_ATTEMPTS:
        remaining = attempt.seconds_remaining()
        messages.error(request, LOCKED_MESSAGE)
        return render(request, 'auth/login.html', {'locked': True, 'remaining': remaining})

    remaining_attempts = MAX_FAILED_ATTEMPTS - attempt.failed_count
    messages.error(request, f'{INVALID_LOGIN_MESSAGE} {remaining_attempts} attempts remaining.')
    return render(request, 'auth/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


DAY_LABELS = {
    1: 'Monday',
    2: 'Tuesday',
    3: 'Wednesday',
    4: 'Thursday',
    5: 'Friday',
    6: 'Saturday',
    7: 'Sunday',
}
PX_PER_HOUR = 44
GRID_PAD = 10


def _hours_between(start, end):
    return ((end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)) / 60.0


def _fmt_hours(value):
    return f'{value:.0f}' if abs(value - round(value)) < 0.01 else f'{value:.1f}'


def _collect_conflicts(schedules):
    """Return every teacher, room and section double-booking in ``schedules``."""
    by_day = {}
    for sched in schedules:
        by_day.setdefault(sched.day_of_week, []).append(sched)

    found = []
    for day, items in by_day.items():
        items.sort(key=lambda s: s.start_time)
        for index, first in enumerate(items):
            for second in items[index + 1:]:
                if second.start_time >= first.end_time:
                    break
                for field, label in (('teacher', 'Teacher'), ('room', 'Room'), ('section', 'Section')):
                    if getattr(first, f'{field}_id') != getattr(second, f'{field}_id'):
                        continue
                    if field == 'teacher':
                        resource = f'{first.teacher.first_name} {first.teacher.last_name}'.strip()
                    elif field == 'room':
                        resource = f'{first.room.building.code} · {first.room.room_name}'
                    else:
                        resource = first.section.name
                    found.append({
                        'kind': label,
                        'resource': resource,
                        'day': DAY_LABELS[day],
                        'time': f'{first.start_time:%H:%M}–{second.end_time:%H:%M}',
                        'codes': f'{first.subject.code} & {second.subject.code}',
                    })
    return found


@login_required(login_url='login')
def home(request):
    semester = (
        Semester.objects.select_related('curriculum__program')
        .filter(is_active=True, curriculum__is_active=True)
        .first()
    )

    role = get_user_role(request.user)
    faculty = Faculty.objects.filter(user=request.user).first() if role == ROLE_TEACHER else None
    teacher_mode = faculty is not None
    teacher_without_profile = role == ROLE_TEACHER and faculty is None

    semester_schedules = Schedule.objects.none()
    scoped = Schedule.objects.none()
    sections = Section.objects.none()
    selected_section = None

    if semester:
        semester_schedules = Schedule.objects.filter(semester=semester).select_related(
            'subject', 'section', 'room__building', 'teacher'
        )
        if teacher_mode:
            scoped = semester_schedules.filter(teacher=faculty)
            sections = (
                Section.objects.filter(schedules__teacher=faculty, schedules__semester=semester)
                .distinct()
                .order_by('program__program_code', 'year_level', 'name')
            )
        else:
            scoped = semester_schedules
            sections = Section.objects.filter(semester=semester, is_active=True).order_by(
                'program__program_code', 'year_level', 'name'
            )

        if not teacher_mode:
            raw_section = request.GET.get('section')
            if raw_section:
                selected_section = sections.filter(pk=raw_section).first()
            if selected_section is None and sections.exists():
                selected_section = sections.first()

    if teacher_mode:
        timetable = list(scoped)
    elif selected_section:
        timetable = list(semester_schedules.filter(section=selected_section))
    else:
        timetable = list(semester_schedules)

    offered_subjects = Subject.objects.none()
    required_hours = 0
    if selected_section and semester:
        offered_subjects = Subject.objects.filter(
            program=selected_section.program,
            semester=semester,
            year_level=selected_section.year_level,
        )
        required_hours = sum(subject.total_weekly_hours for subject in offered_subjects)

    weekly_hours = sum(_hours_between(s.start_time, s.end_time) for s in timetable)
    subjects_done = len({s.subject_id for s in timetable})

    conflicts = _collect_conflicts(list(scoped))

    room_hours = {}
    for sched in scoped:
        key = (sched.room.building.code, sched.room.room_name)
        room_hours[key] = room_hours.get(key, 0) + _hours_between(sched.start_time, sched.end_time)
    rooms = Room.objects.filter(is_active=True).count()

    if required_hours:
        percent = round(weekly_hours / required_hours * 100)
        hours_note = f'{_fmt_hours(max(required_hours - weekly_hours, 0))}h still to place'
        percent_extra = f'{percent}%'
    else:
        hours_note = f'{len(timetable)} class meeting{"s" if len(timetable) != 1 else ""} this week'
        percent_extra = ''

    if teacher_mode:
        section_count = len({s.section_id for s in timetable})
        coverage = {
            'label': 'Classes this week',
            'icon': 'fa-regular fa-rectangle-list',
            'value': str(len(timetable)),
            'extra': '',
            'note': f'{section_count} section{"s" if section_count != 1 else ""} on your load',
        }
    else:
        total_subjects = offered_subjects.count() if selected_section else subjects_done
        coverage = {
            'label': 'Subjects covered',
            'icon': 'fa-regular fa-rectangle-list',
            'value': f'{subjects_done} / {total_subjects}',
            'extra': '',
            'note': 'Subjects with at least one class this week'
            if selected_section else 'Distinct subjects on the timetable',
        }

    stats = [
        {
            'label': 'Weekly hours scheduled',
            'icon': 'fa-regular fa-clock',
            'value': f'{_fmt_hours(weekly_hours)}h',
            'extra': percent_extra,
            'note': hours_note,
        },
        coverage,
        {
            'label': 'Conflicts detected',
            'icon': 'fa-solid fa-triangle-exclamation',
            'value': str(len(conflicts)),
            'extra': '',
            'note': 'Teacher, room or section double-bookings'
            if conflicts else 'No double-bookings in this semester',
        },
        {
            'label': 'Rooms in use',
            'icon': 'fa-solid fa-door-open',
            'value': f'{len(room_hours)} / {rooms}',
            'extra': '',
            'note': 'Rooms with at least one class',
        },
    ]

    grid_start = 7
    grid_end = 17
    for sched in timetable:
        grid_start = min(grid_start, sched.start_time.hour)
        grid_end = max(grid_end, sched.end_time.hour + (1 if sched.end_time.minute else 0))
    for sched in timetable:
        sched.top_px = round(
            ((sched.start_time.hour * 60 + sched.start_time.minute) / 60 - grid_start) * PX_PER_HOUR
        ) + GRID_PAD
        sched.height_px = max(round(_hours_between(sched.start_time, sched.end_time) * PX_PER_HOUR - 4), 24)
        sched.time_label = f'{sched.start_time:%H:%M}–{sched.end_time:%H:%M}'

    time_labels = [
        {'text': f'{hour:02d}:00', 'top': (hour - grid_start) * PX_PER_HOUR + GRID_PAD}
        for hour in range(grid_start, grid_end + 1)
    ]
    day_columns = [
        {'name': name, 'events': [s for s in timetable if s.day_of_week == num]}
        for num, name in DAY_LABELS.items()
    ]

    attention = [
        {
            'tone': 'r',
            'icon': '!',
            'tag': 'Conflict',
            'tag_tone': 'r',
            'title': f"{conflict['codes']} · {conflict['day']} {conflict['time']}",
            'detail': f"{conflict['kind']} overlap on {conflict['resource']}.",
            'action': 'Review schedules',
        }
        for conflict in conflicts[:4]
    ]
    if not teacher_mode and len(attention) < 4 and semester:
        busy_sections = set(scoped.values_list('section_id', flat=True))
        for section in sections:
            if len(attention) >= 4:
                break
            if section.id in busy_sections:
                continue
            attention.append({
                'tone': 'a',
                'icon': '+',
                'tag': 'Empty',
                'tag_tone': 'a',
                'title': f'{section.name} · no classes yet',
                'detail': f'{section.program.program_code} · Year {section.year_level}',
                'action': 'Build its timetable',
            })

    scheduled_lecture = {}
    scheduled_lab = {}
    for sched in timetable:
        bucket = scheduled_lab if sched.class_type == 'Laboratory' else scheduled_lecture
        bucket[sched.subject_id] = bucket.get(sched.subject_id, 0) + _hours_between(
            sched.start_time, sched.end_time
        )
    complete_subjects = sum(
        1 for subject in offered_subjects
        if scheduled_lecture.get(subject.id, 0) >= subject.lec_hours
        and scheduled_lab.get(subject.id, 0) >= subject.lab_hours
    )

    if offered_subjects:
        foot_left = (
            f'{complete_subjects} of {offered_subjects.count()} offered subjects meet their weekly '
            'lecture and laboratory hours.'
        )
    else:
        foot_left = f'{len(timetable)} classes on the timetable this week.'

    room_rows = sorted(room_hours.items(), key=lambda item: item[1], reverse=True)[:4]
    room_rows = [
        {
            'name': f'{building} · {room_name}',
            'hours': _fmt_hours(hours),
            'percent': round(hours / 40 * 100),
            'bar_width': min(round(hours / 40 * 100), 100),
        }
        for (building, room_name), hours in room_rows
    ]

    if conflicts:
        badge = {'text': f'{len(conflicts)} conflict{"s" if len(conflicts) != 1 else ""} to resolve', 'ok': False}
    else:
        badge = {'text': 'Schedule healthy', 'ok': True}

    return render(request, 'home.html', {
        'semester': semester,
        'teacher_mode': teacher_mode,
        'teacher_without_profile': teacher_without_profile,
        'sections': sections,
        'selected_section': selected_section,
        'scope_label': (
            'My teaching load' if teacher_mode
            else selected_section.name if selected_section
            else 'All sections'
        ),
        'stats': stats,
        'timetable': timetable,
        'day_columns': day_columns,
        'time_labels': time_labels,
        'grid_height': (grid_end - grid_start) * PX_PER_HOUR + GRID_PAD,
        'conflicts': conflicts,
        'attention': attention,
        'badge': badge,
        'foot_left': foot_left,
        'foot_right': (
            f'Semester {semester.semester_number} · {semester.curriculum.academic_year}'
            if semester else ''
        ),
        'room_rows': room_rows,
    })


@require_http_methods(['GET', 'POST'])
def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'GET':
        return render(request, 'auth/register.html')

    form_data = {
        'username': request.POST.get('username', ''),
        'first_name': request.POST.get('first_name', ''),
        'last_name': request.POST.get('last_name', ''),
        'email': request.POST.get('email', ''),
        'password': request.POST.get('password', ''),
        'confirm_password': request.POST.get('confirm_password', ''),
    }

    errors = _validate_registration_data(form_data)
    if errors:
        return render(request, 'auth/register.html', {'errors': errors, 'form_data': form_data})

    user = User.objects.create_user(
        username=form_data['username'].strip(),
        first_name=form_data['first_name'].strip(),
        last_name=form_data['last_name'].strip(),
        email=form_data['email'].strip(),
        password=form_data['password'],
    )
    login(request, user)
    return redirect('dashboard')
