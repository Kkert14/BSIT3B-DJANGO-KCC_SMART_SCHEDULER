"""Round-trip tests for the Excel export/import feature.

Each test exports the current data, feeds the file straight back into the
matching import endpoint, and asserts that nothing is lost, duplicated or
rejected. These tests are the regression net for the header/title/time
handling in ``apps.utils.import_export``.
"""

import io

from django.contrib.auth import get_user_model
from django.test import TestCase
from openpyxl import Workbook

from apps.building.models import Building
from apps.program.models import Program
from apps.rooms.models import Room
from apps.schedule.models import Schedule
from apps.section.models import Section
from apps.subject.models import Subject
from apps.teacher.models import Teacher
from apps.users.models import UserProfile
from apps.utils.import_export import (
    excel_to_dict_list,
    get_str,
    get_value,
    normalize_header,
    parse_bool,
    parse_time,
)

User = get_user_model()


class ImportExportHelperTests(TestCase):
    """Unit tests for the header/value helpers."""

    def test_normalize_header_collapses_relationship_separators(self):
        self.assertEqual(
            normalize_header('Teacher Employee Number'), 'teacher_employee_number'
        )
        self.assertEqual(
            normalize_header('teacher__employee_number'), 'teacher_employee_number'
        )
        self.assertEqual(normalize_header('Building Code'), 'building_code')
        self.assertEqual(normalize_header('  ROOM  Room Name '), 'room_room_name')
        self.assertEqual(normalize_header('is_active'), 'is_active')

    def test_get_str_accepts_both_header_spellings(self):
        row = {'teacher_employee_number': 'EMP-1'}
        self.assertEqual(get_str(row, 'teacher__employee_number'), 'EMP-1')
        self.assertEqual(get_str(row, 'teacher_employee_number'), 'EMP-1')

    def test_get_str_returns_blank_for_empty_cells(self):
        """A blank cell must not become the string 'None'."""
        row = {'prerequisite_code': None}
        self.assertEqual(get_str(row, 'prerequisite_code'), '')

    def test_get_str_honours_default(self):
        self.assertEqual(get_str({}, 'role', 'student'), 'student')

    def test_parse_time_accepts_both_representations(self):
        from datetime import time
        self.assertEqual(parse_time('08:00'), time(8, 0))
        self.assertEqual(parse_time('08:00:00'), time(8, 0))
        self.assertEqual(parse_time(time(8, 0)), time(8, 0))
        self.assertIsNone(parse_time('nonsense'))
        self.assertIsNone(parse_time(None))

    def test_parse_bool(self):
        self.assertTrue(parse_bool(True))
        self.assertTrue(parse_bool('TRUE'))
        self.assertTrue(parse_bool('yes'))
        self.assertFalse(parse_bool('no'))
        self.assertTrue(parse_bool(None, default=True))

    def test_title_row_is_skipped(self):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(['Buildings Export'])
        ws.append(['code', 'name', 'is_active'])
        ws.append(['B1', 'Building One', 'true'])
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        rows = excel_to_dict_list(buffer.read())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['code'], 'B1')
        self.assertEqual(rows[0]['name'], 'Building One')


class RoundTripTestMixin:
    """Helpers for exporting and re-importing a file."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='rt_admin', password='test-pass-123', is_superuser=True
        )
        UserProfile.objects.get_or_create(user=self.admin, defaults={'role': 'admin'})
        self.client.force_login(self.admin)

    def export(self, url_name):
        response = self.client.get(url_name)
        self.assertEqual(response.status_code, 200, f'export {url_name} failed')
        return response.content

    def reimport(self, url_name, content):
        response = self.client.post(
            url_name, {'file': io.BytesIO(content)}, HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200, f'import {url_name} failed')
        return response.json()


class BuildingRoundTripTests(RoundTripTestMixin, TestCase):
    def test_export_then_import(self):
        Building.objects.create(code='RT_B1', name='RT Building One', is_active=True)
        Building.objects.create(code='RT_B2', name='RT Building Two', is_active=False)

        content = self.export('/buildings/export/excel/')
        result = self.reimport('/buildings/import/excel/', content)

        self.assertEqual(result['errors'], [], f'import reported errors: {result["errors"]}')
        self.assertEqual(Building.objects.count(), 2)
        b1 = Building.objects.get(code='RT_B1')
        self.assertEqual(b1.name, 'RT Building One')
        self.assertTrue(b1.is_active)
        b2 = Building.objects.get(code='RT_B2')
        self.assertFalse(b2.is_active)


class ProgramRoundTripTests(RoundTripTestMixin, TestCase):
    def test_export_then_import(self):
        Program.objects.create(code='RT_P1', name='RT Program One', is_active=True)

        content = self.export('/programs/export/excel/')
        result = self.reimport('/programs/import/excel/', content)

        self.assertEqual(result['errors'], [])
        self.assertEqual(Program.objects.count(), 1)
        self.assertEqual(Program.objects.get(code='RT_P1').name, 'RT Program One')


class RoomRoundTripTests(RoundTripTestMixin, TestCase):
    def test_export_then_import(self):
        building = Building.objects.create(code='RT_MB', name='RT Main Building')
        Room.objects.create(
            building=building, room_name='RT Lab 1',
            room_type='Laboratory', capacity=40, is_active=True,
        )

        content = self.export('/rooms/export/excel/')
        result = self.reimport('/rooms/import/excel/', content)

        self.assertEqual(result['errors'], [])
        self.assertEqual(Room.objects.count(), 1)
        room = Room.objects.get(room_name='RT Lab 1')
        self.assertEqual(room.building.code, 'RT_MB')
        self.assertEqual(room.room_type, 'Laboratory')
        self.assertEqual(room.capacity, 40)


class SectionRoundTripTests(RoundTripTestMixin, TestCase):
    def test_export_then_import(self):
        program = Program.objects.create(code='RT_SP', name='RT Program')
        Section.objects.create(
            program=program, name='RT1A', year_level=1,
            academic_year='2024-2025', capacity=40, is_active=True,
        )

        content = self.export('/sections/export/excel/')
        result = self.reimport('/sections/import/excel/', content)

        self.assertEqual(result['errors'], [])
        self.assertEqual(Section.objects.count(), 1)
        section = Section.objects.get(name='RT1A')
        self.assertEqual(section.program.code, 'RT_SP')
        self.assertEqual(section.year_level, 1)
        self.assertEqual(section.academic_year, '2024-2025')


class SubjectRoundTripTests(RoundTripTestMixin, TestCase):
    def test_export_then_import(self):
        program = Program.objects.create(code='RT_SJ', name='RT Program')
        Subject.objects.create(
            program=program, code='RTCS101', name='RT Intro', units=3,
            lec_hours=3, lab_hours=0, academic_year='2024-2025',
            year_level=1, semester=1,
        )

        content = self.export('/subjects/export/excel/')
        result = self.reimport('/subjects/import/excel/', content)

        self.assertEqual(result['errors'], [])
        self.assertEqual(Subject.objects.count(), 1)
        subject = Subject.objects.get(code='RTCS101')
        self.assertEqual(subject.program.code, 'RT_SJ')
        self.assertEqual(float(subject.units), 3.0)
        self.assertEqual(subject.lec_hours, 3)

    def test_blank_prerequisite_cell_does_not_become_none_string(self):
        program = Program.objects.create(code='RT_SK', name='RT Program')
        Subject.objects.create(
            program=program, code='RTCS102', name='RT Advanced', units=3,
            lec_hours=3, lab_hours=0, academic_year='2024-2025',
            year_level=2, semester=1,
        )

        content = self.export('/subjects/export/excel/')
        result = self.reimport('/subjects/import/excel/', content)

        self.assertEqual(result['errors'], [])
        self.assertIsNone(Subject.objects.get(code='RTCS102').prerequisite)


class TeacherRoundTripTests(RoundTripTestMixin, TestCase):
    def test_export_then_import(self):
        Teacher.objects.create(
            employee_number='RT-EMP-1', first_name='Juan',
            last_name='Dela Cruz', contact_number='09170000000', is_active=True,
        )

        content = self.export('/teachers/export/excel/')
        result = self.reimport('/teachers/import/excel/', content)

        self.assertEqual(result['errors'], [])
        self.assertEqual(Teacher.objects.count(), 1)
        teacher = Teacher.objects.get(employee_number='RT-EMP-1')
        self.assertEqual(teacher.first_name, 'Juan')
        self.assertEqual(teacher.last_name, 'Dela Cruz')

    def test_optional_user_link_round_trips(self):
        linked = User.objects.create_user(username='rt_teacher_user', password='pw12345678')
        Teacher.objects.create(
            employee_number='RT-EMP-2', first_name='Maria', last_name='Santos',
            contact_number='', is_active=True, user=linked,
        )

        content = self.export('/teachers/export/excel/')
        result = self.reimport('/teachers/import/excel/', content)

        self.assertEqual(result['errors'], [])
        self.assertEqual(Teacher.objects.get(employee_number='RT-EMP-2').user, linked)


class UserRoundTripTests(RoundTripTestMixin, TestCase):
    def test_export_then_import(self):
        staff = User.objects.create_user(
            username='rt_staff', password='pw12345678', first_name='Ana',
            last_name='Reyes', email='ana@example.com',
        )
        UserProfile.objects.get_or_create(user=staff, defaults={'role': 'teacher'})
        staff.profile.role = 'teacher'
        staff.profile.save()

        content = self.export('/users/export/excel/')
        result = self.reimport('/users/import/excel/', content)

        self.assertEqual(result['errors'], [])
        reloaded = User.objects.get(username='rt_staff')
        self.assertEqual(reloaded.profile.role, 'teacher')


class ScheduleRoundTripTests(RoundTripTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        program = Program.objects.create(code='RT_SP2', name='RT Program')
        building = Building.objects.create(code='RT_SB', name='RT Building')
        self.room = Room.objects.create(
            building=building, room_name='RT Room 1',
            room_type='Classroom', capacity=40,
        )
        self.teacher = Teacher.objects.create(
            employee_number='RT-EMP-9', first_name='Ana', last_name='Reyes',
            contact_number='', is_active=True,
        )
        self.subject = Subject.objects.create(
            program=program, code='RTCS201', name='RT Subject', units=3,
            lec_hours=3, lab_hours=0, academic_year='2024-2025',
            year_level=1, semester=1,
        )
        self.section = Section.objects.create(
            program=program, name='RT2A', year_level=1,
            academic_year='2024-2025', capacity=40,
        )

    def test_export_then_import(self):
        Schedule.objects.create(
            academic_year='2024-2025', semester=1, teacher=self.teacher,
            subject=self.subject, section=self.section, room=self.room,
            class_type='Lecture', day_of_week=1,
            start_time='08:00', end_time='09:00',
        )

        content = self.export('/schedules/export/excel/')
        result = self.reimport('/schedules/import/excel/', content)

        self.assertEqual(result['errors'], [], f'import reported errors: {result["errors"]}')
        self.assertEqual(Schedule.objects.count(), 1)
        schedule = Schedule.objects.get()
        self.assertEqual(schedule.teacher.employee_number, 'RT-EMP-9')
        self.assertEqual(schedule.subject.code, 'RTCS201')
        self.assertEqual(schedule.section.name, 'RT2A')
        self.assertEqual(schedule.room.room_name, 'RT Room 1')
        self.assertEqual(schedule.start_time.strftime('%H:%M'), '08:00')
        self.assertEqual(schedule.end_time.strftime('%H:%M'), '09:00')
        self.assertEqual(schedule.day_of_week, 1)

    def test_export_carries_the_disambiguating_columns(self):
        """Program/building codes are needed to identify related rows."""
        Schedule.objects.create(
            academic_year='2024-2025', semester=1, teacher=self.teacher,
            subject=self.subject, section=self.section, room=self.room,
            class_type='Lecture', day_of_week=1,
            start_time='08:00', end_time='09:00',
        )
        content = self.export('/schedules/export/excel/')
        rows = excel_to_dict_list(content)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['subject_program_code'], 'RT_SP2')
        self.assertEqual(rows[0]['section_program_code'], 'RT_SP2')
        self.assertEqual(rows[0]['room_building_code'], 'RT_SB')

    def _schedule_sheet(self, **overrides):
        row = {
            'academic_year': '2024-2025',
            'semester': 1,
            'teacher__employee_number': 'RT-EMP-9',
            'subject__code': 'RTCS201',
            'subject__program__code': 'RT_SP2',
            'section__name': 'RT2A',
            'section__program__code': 'RT_SP2',
            'room__room_name': 'RT Room 1',
            'room__building__code': 'RT_SB',
            'class_type': 'Lecture',
            'day_of_week': 1,
            'start_time': '08:00',
            'end_time': '09:00',
        }
        row.update(overrides)
        return row

    def _import_rows(self, rows):
        """Build a sheet from ``rows`` and post it to the import endpoint."""
        workbook = Workbook()
        sheet = workbook.active
        headers = list(rows[0].keys())
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(header) for header in headers])
        buffer = io.BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return self.reimport('/schedules/import/excel/', buffer.read())

    def test_import_rejects_a_teacher_double_booking(self):
        """The import must apply the same conflict rules as the UI."""
        program = Program.objects.get(code='RT_SP2')
        other_subject = Subject.objects.create(
            program=program, code='RTCS202', name='RT Other Subject', units=3,
            lec_hours=3, lab_hours=0, academic_year='2024-2025',
            year_level=1, semester=1,
        )
        other_section = Section.objects.create(
            program=program, name='RT2C', year_level=1,
            academic_year='2024-2025', capacity=40,
        )
        other_room = Room.objects.create(
            building=Building.objects.get(code='RT_SB'), room_name='RT Room 2',
            room_type='Classroom', capacity=40,
        )
        Schedule.objects.create(
            academic_year='2024-2025', semester=1, teacher=self.teacher,
            subject=self.subject, section=self.section, room=self.room,
            class_type='Lecture', day_of_week=1,
            start_time='08:00', end_time='09:00',
        )

        # Same teacher, overlapping time, but a different subject/section/room.
        result = self._import_rows([self._schedule_sheet(
            subject__code='RTCS202',
            section__name='RT2C',
            room__room_name='RT Room 2',
            start_time='08:30',
            end_time='09:30',
        )])

        self.assertEqual(result['created'], 0)
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('already teaching', result['errors'][0])
        self.assertEqual(Schedule.objects.count(), 1)

    def test_import_rejects_a_room_double_booking(self):
        other_teacher = Teacher.objects.create(
            employee_number='RT-EMP-10', first_name='Bob', last_name='Reyes',
            contact_number='', is_active=True,
        )
        other_section = Section.objects.create(
            program=Program.objects.get(code='RT_SP2'), name='RT2B',
            year_level=1, academic_year='2024-2025', capacity=40,
        )
        Schedule.objects.create(
            academic_year='2024-2025', semester=1, teacher=self.teacher,
            subject=self.subject, section=self.section, room=self.room,
            class_type='Lecture', day_of_week=1,
            start_time='08:00', end_time='09:00',
        )

        result = self._import_rows([self._schedule_sheet(
            teacher__employee_number='RT-EMP-10',
            section__name='RT2B',
        )])

        self.assertEqual(result['created'], 0)
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('already used', result['errors'][0])
        self.assertEqual(Schedule.objects.count(), 1)

    def test_import_reports_an_ambiguous_subject_instead_of_crashing(self):
        """Two subjects sharing a code must not raise MultipleObjectsReturned."""
        Program.objects.create(code='RT_SP9', name='RT Other Program')
        Subject.objects.create(
            program=Program.objects.get(code='RT_SP9'), code='RTCS201',
            name='RT Subject In Another Program', units=3, lec_hours=3,
            lab_hours=0, academic_year='2024-2025', year_level=1, semester=1,
        )

        result = self._import_rows([self._schedule_sheet(
            subject__program__code='',
        )])

        self.assertEqual(result['created'], 0)
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('ambiguous', result['errors'][0])
        self.assertEqual(Schedule.objects.count(), 0)

    def test_import_resolves_an_ambiguous_subject_using_the_program_code(self):
        Program.objects.create(code='RT_SP9', name='RT Other Program')
        Subject.objects.create(
            program=Program.objects.get(code='RT_SP9'), code='RTCS201',
            name='RT Subject In Another Program', units=3, lec_hours=3,
            lab_hours=0, academic_year='2024-2025', year_level=1, semester=1,
        )

        result = self._import_rows([self._schedule_sheet()])

        self.assertEqual(result['errors'], [])
        self.assertEqual(result['created'], 1)
        self.assertEqual(Schedule.objects.get().subject.program.code, 'RT_SP2')

    def test_import_reports_a_missing_related_row(self):
        result = self._import_rows([self._schedule_sheet(
            teacher__employee_number='RT-NOBODY',
        )])

        self.assertEqual(result['created'], 0)
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('not found', result['errors'][0])
