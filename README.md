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
| openpyxl | 3.1.5 | Excel import/export |

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

| Role | Read | Create / edit / delete | Export | Import |
|---|---|---|---|---|
| Administrator | yes | yes | yes | yes |
| Teacher | yes | no | no | no |
| Student | yes | no | no | no |

Role lives on `UserProfile.role`. Superusers bypass every check. The write
controls are hidden from the UI for non-admins, and the API returns `403` with
a JSON error.

## Excel import / export

Every list page can export to `.xlsx` and import back. The export writes a
title row, a header row and the data; the importer recognises that format and
also accepts a hand-written file whose first row is the header.

Related columns are identified by their full path, so the schedule export
carries `Subject Program Code` and `Room Building Code` as well - subject
codes, section names and room names repeat across programs and buildings.

Imports run through the same validation as the UI, so a spreadsheet cannot
create a double booking. Rows that fail are reported per row rather than
aborting the whole file.

A manual smoke check is available:

```bash
python scripts/manual_export_import_check.py
```

It talks to the real development database and creates and removes a couple of
`SMOKE_*` rows.

## Tests

```bash
python manage.py test        # Django test runner
python -m pytest             # pytest
```

Both runners discover the same 52 tests.
