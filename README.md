# Smart Scheduler

A class scheduling system for a college: build the master data (buildings,
rooms, programs, subjects, sections, teachers), then place subjects into a
weekly timetable while the app checks for double bookings.

## Members

Kert Villahermosa
Nhel Segotier
Delmar Velasco

## Requirements

| Component | Version | Notes |
|---|---|---|
| Python | 3.11 or 3.12 | Django 5.0 does not support Python 3.13+ |
| Django | 5.0.14 | 5.1+ requires MariaDB 10.5+ |
| MariaDB / MySQL | 10.4+ / 8.0.11+ | |
| openpyxl | 3.1.5 | Excel report export |

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The database defaults to `smart_scheduler` on `localhost:3306` as `root` with
no password. Override anything with environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | insecure dev key | **Set this in production** |
| `DJANGO_DEBUG` | `True` | Set to `False` in production |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | Comma separated |
| `DJANGO_DB_NAME` | `smart_scheduler` | |
| `DJANGO_DB_USER` | `root` | |
| `DJANGO_DB_PASSWORD` | *(empty)* | |
| `DJANGO_DB_HOST` | `localhost` | |
| `DJANGO_DB_PORT` | `3306` | |
| `DJANGO_SECURE_SSL_REDIRECT` | `not DEBUG` | |

With `DJANGO_DEBUG=False` the app enables secure cookies, HTTPS redirects and
HSTS automatically.

## Roles

| Role | Read | Create / edit / delete |
|---|---|---|
| Administrator | yes | yes |
| Teacher | yes | no |
| Student | yes | no |

Role lives on `UserProfile.role`. Superusers bypass every check. The write
controls are hidden from the UI for non-admins, and the API returns `403` with
a JSON error.

Schedule reports (master list, section timetable, faculty schedule) are open to
administrators and to teachers whose account is linked to a faculty record;
teachers only ever see their own load.

## Tests

```bash
python manage.py test        # Django test runner
python -m pytest             # pytest
```

Both runners discover the same 38 tests.
