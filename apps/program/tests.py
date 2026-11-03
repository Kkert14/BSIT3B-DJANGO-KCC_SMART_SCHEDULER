from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.curriculum.models import Curriculum, Semester
from apps.subject.models import Subject

from .models import Program

User = get_user_model()


class ProgramCoursesYearTests(TestCase):
    """The Courses page follows the active curriculum by default."""

    @classmethod
    def setUpTestData(cls):
        cls.active_year = Curriculum.objects.create(
            code='2025-2026', name='Curriculum 2025-2026',
            academic_year='2025-2026', is_active=True,
        )
        cls.other_year = Curriculum.objects.create(
            code='2024-2025', name='Curriculum 2024-2025',
            academic_year='2024-2025', is_active=False,
        )
        cls.other_semester = Semester.objects.create(
            curriculum=cls.other_year, semester_number=1, is_active=False,
        )
        cls.active_semester = Semester.objects.create(
            curriculum=cls.active_year, semester_number=1, is_active=True,
        )
        cls.program = Program.objects.create(
            program_code='BSIT', program_description='BS Information Technology',
        )
        cls.other_subject = Subject.objects.create(
            code='OLD101', name='Previous Curriculum Course', units=3,
            lecture_hours=3, program=cls.program, semester=cls.other_semester,
            year_level=1,
        )
        cls.user = User.objects.create_user(username='course_viewer', password='test-pass-123')

    def get_page(self, **params):
        self.client.force_login(self.user)
        return self.client.get(
            reverse('program:program_courses', args=[self.program.id]), params
        )

    def test_defaults_to_the_active_curriculum(self):
        response = self.get_page()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['filter_year'], str(self.active_year.id))
        self.assertNotContains(response, 'OLD101')

    def test_year_parameter_still_overrides_the_default(self):
        response = self.get_page(year=self.other_year.id)
        self.assertEqual(response.context['filter_year'], str(self.other_year.id))
        self.assertContains(response, 'OLD101')
