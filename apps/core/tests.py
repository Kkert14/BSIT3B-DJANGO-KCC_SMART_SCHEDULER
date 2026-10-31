from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import AppearanceSettings
from apps.curriculum.models import Curriculum, Semester
from apps.users.models import UserProfile


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


class AppearanceSettingsTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username='appearance_admin', password='secret1234',
        )
        profile, _ = UserProfile.objects.get_or_create(
            user=self.admin, defaults={'role': 'admin'},
        )
        profile.role = 'admin'
        profile.save()
        # The profile signal caches the created (student) row on the user
        # instance, so drop it before force_login re-saves last_login.
        self.admin._state.fields_cache.pop('profile', None)
        self.client.force_login(self.admin)

    def test_defaults_are_not_written_on_read(self):
        appearance = AppearanceSettings.load()

        self.assertIsNone(appearance.pk)
        self.assertEqual(appearance.theme, 'light')
        self.assertEqual(appearance.accent, '#2b8be6')
        self.assertEqual(appearance.font, 'segoe')
        self.assertEqual(appearance.accent_rgb, '43, 139, 230')
        self.assertIn('Segoe UI', appearance.font_stack)
        self.assertFalse(AppearanceSettings.objects.exists())

    def test_save_creates_and_reuses_the_singleton(self):
        response = self.client.post(reverse('curriculum:appearance_save'), {
            'theme': 'dark', 'accent': '#E11D48', 'font': 'inter',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['accent'], '#e11d48')
        self.assertEqual(response.json()['accent_rgb'], '225, 29, 72')

        self.client.post(reverse('curriculum:appearance_save'), {
            'theme': 'light', 'accent': '#0d9488', 'font': 'poppins',
        })
        self.assertEqual(AppearanceSettings.objects.count(), 1)
        appearance = AppearanceSettings.objects.get()
        self.assertEqual(appearance.theme, 'light')
        self.assertEqual(appearance.accent, '#0d9488')
        self.assertEqual(appearance.font, 'poppins')

    def test_invalid_values_are_rejected(self):
        payloads = (
            {'theme': 'sepia', 'accent': '#2b8be6', 'font': 'segoe'},
            {'theme': 'light', 'accent': 'blue', 'font': 'segoe'},
            {'theme': 'light', 'accent': '#2b8be6', 'font': 'comic-sans'},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    reverse('curriculum:appearance_save'), payload,
                )
                self.assertEqual(response.status_code, 400)

        self.assertFalse(AppearanceSettings.objects.exists())

    def test_non_admin_cannot_save(self):
        student = get_user_model().objects.create_user(
            username='appearance_student', password='secret1234',
        )
        profile, _ = UserProfile.objects.get_or_create(
            user=student, defaults={'role': 'student'},
        )
        profile.role = 'student'
        profile.save()
        student._state.fields_cache.pop('profile', None)
        self.client.force_login(student)

        response = self.client.post(reverse('curriculum:appearance_save'), {
            'theme': 'dark', 'accent': '#e11d48', 'font': 'inter',
        })

        self.assertEqual(response.status_code, 403)
        self.assertFalse(AppearanceSettings.objects.exists())

    def test_settings_page_renders_the_appearance_card(self):
        response = self.client.get(reverse('curriculum:curriculum_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="appearanceForm"')
        self.assertContains(response, 'data-accent="#2b8be6"')
        self.assertContains(response, 'data-accent="#6366f1"')
        self.assertContains(response, 'Curriculum')

    def test_saved_appearance_is_applied_to_the_document(self):
        AppearanceSettings.objects.create(
            theme='dark', accent='#e11d48', font='poppins',
        )

        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'data-bs-theme="dark"')
        self.assertContains(response, '--ss-blue: #e11d48')
        self.assertContains(response, '--tblr-primary-rgb: 225, 29, 72')
        self.assertContains(response, 'family=Poppins')

    def test_light_theme_loads_no_google_font(self):
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'data-bs-theme="light"')
        self.assertNotContains(response, 'fonts.googleapis.com')
