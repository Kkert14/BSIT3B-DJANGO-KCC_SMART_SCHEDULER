from datetime import timedelta
from zoneinfo import ZoneInfo

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
# Class times are local school time; the project default of UTC would shift "today".
SCHOOL_TIME_ZONE = ZoneInfo('Asia/Manila')


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


def _dashboard_hero(schedules, today_classes, today_number, now_minutes, teacher_mode=False):
    """The class to highlight: happening now, next today, or the next class day."""
    ongoing = None
    upcoming = None
    for sched in today_classes:
        start = sched.start_time.hour * 60 + sched.start_time.minute
        end = sched.end_time.hour * 60 + sched.end_time.minute
        if start <= now_minutes < end and ongoing is None:
            ongoing = sched
        elif start > now_minutes and upcoming is None:
            upcoming = sched

    if ongoing is not None:
        return {'label': 'Happening now', 'state': 'now', 'schedule': ongoing}
    if upcoming is not None:
        return {'label': 'Next class today', 'state': 'next', 'schedule': upcoming}
    if today_classes:
        count = len(today_classes)
        return {
            'label': 'Today',
            'state': 'done',
            'title': 'All classes are done for today',
            'message': f'{count} class meeting{"s" if count != 1 else ""} completed.',
        }

    for offset in range(1, 8):
        day_number = (today_number - 1 + offset) % 7 + 1
        day_classes = [sched for sched in schedules if sched.day_of_week == day_number]
        if not day_classes:
            continue
        first = min(day_classes, key=lambda sched: sched.start_time)
        return {
            'label': 'Today',
            'state': 'empty',
            'title': 'No classes today',
            'message': (
                f'Next class is {DAY_LABELS[day_number]} at '
                f'{first.start_time:%H:%M} — {first.subject.code}.'
            ),
        }

    return {
        'label': 'Today',
        'state': 'empty',
        'title': 'No classes today',
        'message': (
            'You have no classes scheduled yet this semester.'
            if teacher_mode else 'No classes have been scheduled yet this semester.'
        ),
    }


@login_required(login_url='login')
def home(request):
    semester = (
        Semester.objects.select_related('curriculum')
        .filter(is_active=True, curriculum__is_active=True)
        .first()
    )

    role = get_user_role(request.user)
    faculty = Faculty.objects.filter(user=request.user).first() if role == ROLE_TEACHER else None
    teacher_mode = faculty is not None
    teacher_without_profile = role == ROLE_TEACHER and faculty is None

    schedules = []
    if semester:
        queryset = Schedule.objects.filter(semester=semester).select_related(
            'subject', 'section', 'room__building', 'teacher'
        )
        if teacher_mode:
            queryset = queryset.filter(teacher=faculty)
        schedules = list(queryset)

    now = timezone.localtime(timezone=SCHOOL_TIME_ZONE)
    today_number = now.isoweekday()
    now_minutes = now.hour * 60 + now.minute

    today_classes = sorted(
        (sched for sched in schedules if sched.day_of_week == today_number),
        key=lambda sched: sched.start_time,
    )
    hero = _dashboard_hero(
        schedules, today_classes, today_number, now_minutes, teacher_mode
    )

    marked_next = False
    for sched in today_classes:
        start = sched.start_time.hour * 60 + sched.start_time.minute
        end = sched.end_time.hour * 60 + sched.end_time.minute
        if end <= now_minutes:
            sched.day_status = 'done'
            sched.day_status_label = 'Done'
        elif start <= now_minutes < end:
            sched.day_status = 'now'
            sched.day_status_label = 'Now'
        elif not marked_next:
            sched.day_status = 'next'
            sched.day_status_label = 'Next'
            marked_next = True
        else:
            sched.day_status = ''
            sched.day_status_label = ''

    weekly_hours = sum(_hours_between(s.start_time, s.end_time) for s in schedules)
    subjects_done = len({s.subject_id for s in schedules})
    conflicts = _collect_conflicts(schedules)

    room_hours = {}
    for sched in schedules:
        key = (sched.room.building.code, sched.room.room_name)
        room_hours[key] = room_hours.get(key, 0) + _hours_between(sched.start_time, sched.end_time)
    rooms = Room.objects.filter(is_active=True).count()

    offered_total = Subject.objects.filter(semester=semester).count() if semester else 0

    if teacher_mode:
        section_count = len({s.section_id for s in schedules})
        coverage = {
            'label': 'Classes this week',
            'icon': 'fa-regular fa-rectangle-list',
            'value': str(len(schedules)),
            'extra': '',
            'note': f'{section_count} section{"s" if section_count != 1 else ""} on your load',
        }
    else:
        coverage = {
            'label': 'Courses covered',
            'icon': 'fa-regular fa-rectangle-list',
            'value': (
                f'{subjects_done} / {offered_total}' if offered_total else str(subjects_done)
            ),
            'extra': '',
            'note': (
                'Courses with at least one class this semester'
                if offered_total else 'Distinct courses on the timetable'
            ),
        }

    stats = [
        {
            'label': 'Weekly hours scheduled',
            'icon': 'fa-regular fa-clock',
            'value': f'{_fmt_hours(weekly_hours)}h',
            'extra': '',
            'note': (
                f'{len(schedules)} class meeting'
                f'{"s" if len(schedules) != 1 else ""} this semester'
            ),
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
            'note': (
                'Rooms with at least one class on your load'
                if teacher_mode else 'Rooms with at least one class'
            ),
        },
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
        busy_sections = {sched.section_id for sched in schedules}
        empty_sections = (
            Section.objects.filter(semester=semester, is_active=True)
            .select_related('program')
            .order_by('program__program_code', 'year_level', 'name')
        )
        for section in empty_sections:
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

    day_numbers = list(range(1, 7))
    if any(sched.day_of_week == 7 for sched in schedules):
        day_numbers.append(7)
    week_days = []
    max_day_hours = 0
    for day_number in day_numbers:
        day_schedules = [sched for sched in schedules if sched.day_of_week == day_number]
        hours = sum(_hours_between(s.start_time, s.end_time) for s in day_schedules)
        max_day_hours = max(max_day_hours, hours)
        week_days.append({
            'name': DAY_LABELS[day_number][:3],
            'classes': len(day_schedules),
            'hours': hours,
        })
    for day in week_days:
        day['hours_label'] = _fmt_hours(day['hours'])
        day['bar_width'] = round(day['hours'] / max_day_hours * 100) if max_day_hours else 0

    if conflicts:
        badge = {'text': f'{len(conflicts)} conflict{"s" if len(conflicts) != 1 else ""} to resolve', 'ok': False}
    else:
        badge = {'text': 'Schedule healthy', 'ok': True}

    if today_classes:
        count = len(today_classes)
        today_label = f'{DAY_LABELS[today_number]} · {count} class meeting{"s" if count != 1 else ""}'
    else:
        today_label = f'{DAY_LABELS[today_number]} · no classes'

    return render(request, 'home.html', {
        'semester': semester,
        'teacher_mode': teacher_mode,
        'teacher_without_profile': teacher_without_profile,
        'stats': stats,
        'conflicts': conflicts,
        'attention': attention,
        'badge': badge,
        'room_rows': room_rows,
        'hero': hero,
        'today_classes': today_classes,
        'today_label': today_label,
        'week_days': week_days,
        'week_summary': (
            f'{len(schedules)} class meeting{"s" if len(schedules) != 1 else ""} · '
            f'{_fmt_hours(weekly_hours)}h this semester'
            if schedules else 'No classes scheduled yet.'
        ),
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
