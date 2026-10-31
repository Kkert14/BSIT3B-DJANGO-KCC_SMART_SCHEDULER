from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.curriculum.models import Curriculum, Semester


class HomeViewTests(TestCase):
    def test_home_renders_for_authenticated_user(self):
        user = get_user_model().objects.create_user(username='admin', password='secret1234')

        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')

    def test_home_requires_login(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 302)

    def test_home_replaces_term_toolbar_and_timetable_with_overview(self):
        user = get_user_model().objects.create_user(username='admin', password='secret1234')
        curriculum = Curriculum.objects.create(academic_year='2025-2026', is_active=True)
        Semester.objects.create(curriculum=curriculum, semester_number=1, is_active=True)

        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Today at a glance')
        self.assertContains(response, 'Week at a glance')
        self.assertNotContains(response, 'Weekly timetable')
        self.assertNotContains(response, 'name="section"')
