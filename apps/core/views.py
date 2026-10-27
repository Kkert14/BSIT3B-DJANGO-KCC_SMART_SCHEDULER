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

from apps.schedule.models import Schedule
from apps.building.models import Building
from apps.program.models import Program
from apps.faculty.models import Faculty
from apps.subject.models import Subject
from apps.section.models import Section
from apps.rooms.models import Room
from apps.users.decorators import is_admin, is_teacher, is_student
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


@login_required(login_url='login')
def home(request):
    # Role-based stats
    if is_admin(request.user):
        stats = {
            'total_buildings': Building.objects.count(),
            'total_programs': Program.objects.count(),
            'total_faculty': Faculty.objects.count(),
            'total_sections': Section.objects.count(),
            'total_subjects': Subject.objects.count(),
            'total_rooms': Room.objects.count(),
            'total_schedules': Schedule.objects.count(),
        }
    elif is_teacher(request.user):
        try:
            teacher = Faculty.objects.get(user=request.user)
            stats = {
                'total_buildings': Building.objects.count(),
                'total_programs': Program.objects.count(),
                'total_faculty': Faculty.objects.count(),
                'total_sections': Section.objects.count(),
                'total_subjects': Subject.objects.count(),
                'total_rooms': Room.objects.count(),
                'total_schedules': Schedule.objects.filter(teacher=teacher).count(),
            }
        except Faculty.DoesNotExist:
            stats = {
                'total_buildings': 0,
                'total_programs': 0,
                'total_faculty': 0,
                'total_sections': 0,
                'total_subjects': 0,
                'total_rooms': 0,
                'total_schedules': 0,
            }
    else:  # student
        stats = {
            'total_buildings': Building.objects.count(),
            'total_programs': Program.objects.count(),
            'total_faculty': Faculty.objects.count(),
            'total_sections': Section.objects.count(),
            'total_subjects': Subject.objects.count(),
            'total_rooms': Room.objects.count(),
            'total_schedules': Schedule.objects.count(),
        }

    return render(request, 'home.html', {
        'stats': stats,
        'user_role': request.user.profile.role if hasattr(request.user, 'profile') else 'student',
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
