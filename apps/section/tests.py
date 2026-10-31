from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.curriculum.models import Curriculum, Semester
from apps.program.models import Program

from .models import Section


class SectionTermScopeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='admin', password='secret1234'
        )
        self.client.force_login(self.user)
        self.program = Program.objects.create(
            program_code='BSIT', program_description='Information Technology'
        )
        self.curriculum = Curriculum.objects.create(
            academic_year='2025-2026', is_active=True
        )
        self.semester = Semester.objects.create(
            curriculum=self.curriculum, semester_number=1, is_active=True
        )
        other_curriculum = Curriculum.objects.create(academic_year='2024-2025')
        self.other_semester = Semester.objects.create(
            curriculum=other_curriculum, semester_number=1
        )
        self.active_section = Section.objects.create(
            name='Alpha',
            program=self.program,
            semester=self.semester,
            year_level=1,
            capacity=40,
        )
        self.other_section = Section.objects.create(
            name='Omega',
            program=self.program,
            semester=self.other_semester,
            year_level=1,
            capacity=40,
        )

    def test_list_only_shows_sections_in_active_term(self):
        response = self.client.get(reverse('section:section_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alpha')
        self.assertNotContains(response, 'Omega')
        self.assertNotContains(response, 'name="semester"')

    def test_save_uses_active_term_without_semester_input(self):
        response = self.client.post(reverse('section:section_save_ajax'), {
            'program': self.program.pk,
            'name': 'Bravo',
            'year_level': 1,
            'capacity': 35,
            'is_active': 'true',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertEqual(
            Section.objects.get(name='Bravo').semester_id, self.semester.pk
        )

    def test_save_requires_an_active_term(self):
        self.curriculum.is_active = False
        self.curriculum.save()
        self.semester.is_active = False
        self.semester.save()

        response = self.client.post(reverse('section:section_save_ajax'), {
            'program': self.program.pk,
            'name': 'Charlie',
            'year_level': 1,
            'capacity': 30,
            'is_active': 'true',
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('top bar', response.json()['error'])
        self.assertFalse(Section.objects.filter(name='Charlie').exists())
