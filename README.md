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

## Concept paper

The formatted submission copy is
`Smart_Scheduler_College_Department_Concept_Paper_Revised.docx` (Letter size,
Times New Roman 12 pt, double-spaced, 1.5" left margin). It follows the
BSIT Class Project Concept Paper Guidelines and describes the system as built
with Django and MariaDB. The same paper is reproduced below.

### DEVELOPMENT OF A WEB-BASED SMART SCHEDULER WITH CONFLICT DETECTION AND SCHEDULE REPORTING FOR A COLLEGE DEPARTMENT

*BSIT Class Project Concept Paper*

**Prepared by:** Kert Villahermosa, Nhel Segotier, Delmar Velasco

#### INTRODUCTION

##### Background of the Project

Scheduling is a recurring administrative task in a college department because class periods, faculty assignments, and classroom allocations must all be arranged within a limited set of time slots and resources. When this work is done through paper records or separate spreadsheet files, department personnel spend considerable time cross-checking availability, updating entries, and communicating changes. A single adjustment to one class may require repeated checking of faculty loads, room bookings, and section timetables, and overlapping assignments are often discovered only after schedules have already been distributed.

To address these difficulties, the proposed project will develop a web-based Smart Scheduler for a college department. The system will provide a centralized record of programs, academic-year curricula and semesters, courses, sections, faculty members, buildings, and rooms. From these records, authorized users will prepare the weekly timetable of a selected term, assign courses to sections with a faculty member and a room, and receive immediate feedback when an entry would double-book a faculty member, a room, or a section. The system will also provide schedule views and printable or downloadable reports so that the department can distribute an organized timetable to the people concerned.

The proposed system will be intended for one selected college department only. It will focus on the scheduling process and on the reference data needed to support it. Student enrollment, grading, attendance monitoring, payroll, and similar academic or administrative functions will remain outside the scope of the project, and the final features will be confirmed with the intended users during development.

##### Statement of the Problem or Project Objectives

The main objective of this project will be to design and develop a web-based Smart Scheduler that will assist a college department in preparing, organizing, and managing class schedules while reducing scheduling conflicts among faculty members, rooms, and sections.

Specifically, the project will aim to:

1. Develop a centralized module for maintaining programs, academic-year curricula and semesters, courses with their units and weekly contact hours, class sections, faculty members, buildings, and rooms.
2. Provide a term-scoped scheduling workspace in which the active academic year and semester are carried across the interface and in which sections, rooms, and faculty can be filtered by program, year level, semester, or building before a class is placed.
3. Allow authorized users to plan a course's weekly load as a batch of day and time slots, check that every slot ends after it starts, prevent overlapping slots within the same plan, and enforce the course's weekly contact-hour limit before the plan is saved as a single transaction.
4. Implement conflict detection that identifies double-booked faculty members, rooms, and sections for the active term, and display the results on the scheduling page and the dashboard.
5. Apply role-based access control for administrators, instructors, and students, enforce the restrictions on the server side, and limit instructor accounts that are linked to a faculty record to their own teaching load.
6. Generate schedule reports in the form of a master list, a section timetable, and a faculty schedule, with table and grid views, print-ready layouts, and Excel export.
7. Evaluate the developed system through testing and user feedback in terms of functionality, usability, and the accuracy of its conflict checks.

##### Significance of the Project

The proposed system will provide practical benefits to the following users:

- **College Department Administrators and Scheduling Coordinators:** the system will keep scheduling records in one place, show the weekly timetable of a term, and identify possible conflicts before schedules are released.
- **Faculty Members:** instructors with a linked account will be able to view their assigned classes, rooms, and time slots without requesting a printed copy from the department.
- **Students:** organized section timetables published by the department will give students a clearer reference for their class schedule.
- **Department Personnel:** authorized staff will maintain program, course, section, faculty, and room records more systematically and will rely less on repeated manual checking.
- **Future Researchers and Student Developers:** the project may serve as a reference for web-based scheduling and resource-allocation projects in educational settings.

##### Alignment with Institutional Research Agenda and Sustainable Development Goals

**Institutional Research Agenda Alignment:** the project will align with an institutional research priority on information technology and digital transformation in educational administration by applying a web-based system to a recurring department process. The specific research-agenda wording will be matched to the official agenda of the institution.

**Sustainable Development Goal Alignment:**

- **SDG 4 - Quality Education:** an organized and accurate class schedule will support the orderly delivery of instruction within the selected department.
- **SDG 9 - Industry, Innovation and Infrastructure:** the project will apply web technology and a relational database to modernize an administrative process and build a reusable digital tool for the department.

#### SCOPE AND LIMITATIONS

##### System Scope and Technical Architecture

The Smart Scheduler will cover the scheduling process of one selected college department. It will maintain the reference data required for scheduling and will allow authorized users to place courses into the weekly timetable of the active academic year and semester. The system will be delivered as a web application with server-rendered pages, role-based accounts, server-side validation, and a relational database. Its intended users will be the department administrator or scheduling coordinator, authorized department staff, instructors who consult their own load, and students who view the schedules published for their section.

| Component | Description and Coverage |
|---|---|
| Core Modules | Dashboard and term overview; Programs for degrees with course management inside each program; Settings for academic-year curricula and semesters; Sections; Faculty; Facilities for buildings and rooms; Info Management for contact records; User Management for accounts and roles; Schedule Management with a weekly plan editor, batch slot planning, and conflict checking; and Reports for the master list, section timetable, and faculty schedule. |
| Technology Stack | Python 3.11 or 3.12 with Django 5.0 for the server-side application; MariaDB 10.4 or later (MySQL 8.0 compatible) for the relational database; HTML5, CSS3, and JavaScript with Bootstrap 5 and the Tabler administrative interface for the front end; Font Awesome for interface icons; and openpyxl for Excel report export. |
| Target Users | Department administrators and scheduling coordinators, authorized department staff, instructors who view their own assigned schedules, and students who view published section schedules. |
| Limitations | The system will be limited to one college department. It will not manage enrollment, grades, attendance, payroll, or learning content. It will check for conflicts but will not generate an optimal timetable automatically, so final placement and approval will remain with department personnel. Reports will be export-only, with no spreadsheet import and no email or SMS delivery. Conflict detection will depend on the completeness and correctness of the records entered. The system will require a hosted server or local network connection, and a mobile application is not included. |

##### Limitations

1. The system will cover only one selected college department and will not manage the schedules of the entire institution or of other departments.
2. The system will focus on class scheduling and its reference data. Student enrollment, grading, attendance monitoring, payroll, and learning management will be outside the project scope.
3. The system will not compute an optimal timetable on its own. It will check the entries made by authorized users and report conflicts, but it will not replace the judgment of the scheduling coordinator.
4. Reports will be limited to on-screen views, printing, and Excel export. Importing schedules from spreadsheets, sending schedules by email or SMS, and synchronizing with other school systems will not be included.
5. The accuracy of conflict detection and of the generated reports will depend on the completeness and correctness of the records entered by authorized users.
6. The system will require access to a hosted server or the department's local network. Offline operation and a dedicated mobile application will not be provided.

#### EXPECTED PROJECT OUTPUT

The expected output will be a functional web-based Smart Scheduler prototype for the selected college department. It will include the scheduling modules described in the preceding section, a relational database for scheduling and reference records, role-based access control, conflict detection for faculty members, rooms, and sections, and print-ready and Excel-exportable schedule reports.

The prototype will be demonstrated with representative department data and evaluated by intended users through testing in terms of functionality, usability, and the accuracy of its conflict checks. Because the system is still under development and has not yet been evaluated, this concept paper will not state results, conclusions, or recommendations.

