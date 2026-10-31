import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import AppearanceSettings, MAX_LOGO_BYTES
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

    def appearance_payload(self, **overrides):
        payload = {
            'theme': 'light',
            'accent': '#2b8be6',
            'font': 'segoe',
            'brand_name': 'Smart Scheduler',
            'brand_tagline': 'Management System',
            'brand_icon': 'fa-gear',
        }
        payload.update(overrides)
        return payload

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
        response = self.client.post(reverse('curriculum:appearance_save'), self.appearance_payload(
            theme='dark', accent='#E11D48', font='inter',
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['accent'], '#e11d48')
        self.assertEqual(response.json()['accent_rgb'], '225, 29, 72')

        self.client.post(reverse('curriculum:appearance_save'), self.appearance_payload(
            theme='light', accent='#0d9488', font='poppins',
        ))
        self.assertEqual(AppearanceSettings.objects.count(), 1)
        appearance = AppearanceSettings.objects.get()
        self.assertEqual(appearance.theme, 'light')
        self.assertEqual(appearance.accent, '#0d9488')
        self.assertEqual(appearance.font, 'poppins')

    def test_invalid_values_are_rejected(self):
        payloads = (
            self.appearance_payload(theme='sepia'),
            self.appearance_payload(accent='blue'),
            self.appearance_payload(font='comic-sans'),
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    reverse('curriculum:appearance_save'), payload,
                )
                self.assertEqual(response.status_code, 400)

        self.assertFalse(AppearanceSettings.objects.exists())

    def test_brand_fields_are_saved_and_rendered(self):
        response = self.client.post(reverse('curriculum:appearance_save'), self.appearance_payload(
            brand_name='Campus Flow',
            brand_tagline='Scheduling Suite',
            brand_icon='fa-calendar-check',
        ))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['brand_name'], 'Campus Flow')
        self.assertEqual(response.json()['brand_icon'], 'fa-calendar-check')

        appearance = AppearanceSettings.objects.get()
        self.assertEqual(appearance.brand_first, 'Campus')
        self.assertEqual(appearance.brand_rest, 'Flow')

        page = self.client.get(reverse('dashboard'))
        self.assertContains(page, '<b id="ssBrandFirst">Campus</b>')
        self.assertContains(page, '> Flow</span>')
        self.assertContains(page, 'Scheduling Suite')
        self.assertContains(page, 'fa-calendar-check')

    def test_invalid_brand_values_are_rejected(self):
        payloads = (
            self.appearance_payload(brand_name=''),
            self.appearance_payload(brand_name='x' * 41),
            self.appearance_payload(brand_tagline='x' * 41),
            self.appearance_payload(brand_icon='fa-not-a-real-icon'),
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

        response = self.client.post(
            reverse('curriculum:appearance_save'),
            self.appearance_payload(theme='dark', accent='#e11d48', font='inter'),
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(AppearanceSettings.objects.exists())

    def test_settings_page_renders_the_appearance_card(self):
        response = self.client.get(reverse('curriculum:curriculum_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="appearanceForm"')
        self.assertContains(response, 'data-accent="#2b8be6"')
        self.assertContains(response, 'data-accent="#6366f1"')
        self.assertContains(response, 'name="brand_name"')
        self.assertContains(response, 'Curriculum')

    def test_settings_page_lists_curriculum_before_appearance(self):
        response = self.client.get(reverse('curriculum:curriculum_list'))
        content = response.content.decode()

        self.assertLess(
            content.index('id="curriculumAlert"'),
            content.index('id="appearanceForm"'),
        )

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

    def test_auth_pages_follow_saved_appearance(self):
        self.client.logout()
        AppearanceSettings.objects.create(
            theme='dark',
            accent='#e11d48',
            font='poppins',
            brand_name='Campus Flow',
            brand_tagline='Scheduling Suite',
            brand_icon='fa-calendar-check',
        )

        for name, heading in (
            ('login', 'Sign in'),
            ('register', 'Create your account'),
        ):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'data-bs-theme="dark"')
                self.assertContains(response, '--tblr-primary: #e11d48')
                self.assertContains(response, 'family=Poppins')
                self.assertContains(response, heading)
                self.assertContains(response, 'Scheduling Suite')
                self.assertContains(response, 'fa-calendar-check')
                self.assertNotContains(response, 'offcanvasSettings')
                self.assertNotContains(response, 'Theme Settings')
                self.assertNotContains(response, 'tabler-theme.js')
                self.assertNotContains(response, 'js/demo.js')


class AppearanceLogoTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(shutil.rmtree, self.media_root, True)
        self.addCleanup(self.override.disable)

        self.admin = get_user_model().objects.create_user(
            username='logo_admin', password='secret1234',
        )
        profile, _ = UserProfile.objects.get_or_create(
            user=self.admin, defaults={'role': 'admin'},
        )
        profile.role = 'admin'
        profile.save()
        self.admin._state.fields_cache.pop('profile', None)
        self.client.force_login(self.admin)

    def appearance_payload(self, **overrides):
        payload = {
            'theme': 'light',
            'accent': '#2b8be6',
            'font': 'segoe',
            'brand_name': 'Smart Scheduler',
            'brand_tagline': 'Management System',
            'brand_icon': 'fa-gear',
        }
        payload.update(overrides)
        return payload

    def png(self, name='logo.png'):
        return SimpleUploadedFile(
            name,
            b'\x89PNG\r\n\x1a\n' + b'\x00' * 32,
            content_type='image/png',
        )

    def test_logo_upload_is_stored_and_rendered(self):
        response = self.client.post(
            reverse('curriculum:appearance_save'),
            self.appearance_payload(logo=self.png()),
        )

        self.assertEqual(response.status_code, 200)
        logo_url = response.json()['logo_url']
        self.assertTrue(logo_url.startswith('/media/brand/'))

        appearance = AppearanceSettings.objects.get()
        self.assertTrue((Path(self.media_root) / appearance.logo.name).exists())

        page = self.client.get(reverse('dashboard'))
        self.assertContains(page, f'<img id="ssBrandLogo" src="{logo_url}"')

        settings_page = self.client.get(reverse('curriculum:curriculum_list'))
        self.assertContains(settings_page, f'data-logo-url="{logo_url}"')

    def test_new_logo_deletes_the_old_file(self):
        self.client.post(
            reverse('curriculum:appearance_save'),
            self.appearance_payload(logo=self.png('first.png')),
        )
        first_name = AppearanceSettings.objects.get().logo.name

        self.client.post(
            reverse('curriculum:appearance_save'),
            self.appearance_payload(logo=self.png('second.png')),
        )
        second_name = AppearanceSettings.objects.get().logo.name

        self.assertNotEqual(first_name, second_name)
        self.assertFalse((Path(self.media_root) / first_name).exists())
        self.assertTrue((Path(self.media_root) / second_name).exists())

    def test_logo_can_be_removed(self):
        self.client.post(
            reverse('curriculum:appearance_save'),
            self.appearance_payload(logo=self.png()),
        )
        logo_name = AppearanceSettings.objects.get().logo.name

        response = self.client.post(
            reverse('curriculum:appearance_save'),
            self.appearance_payload(remove_logo='1'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['logo_url'], '')
        self.assertFalse((Path(self.media_root) / logo_name).exists())

    def test_invalid_or_oversized_logo_is_rejected(self):
        payloads = (
            self.appearance_payload(logo=SimpleUploadedFile(
                'logo.png', b'not an image', content_type='image/png',
            )),
            self.appearance_payload(logo=SimpleUploadedFile(
                'huge.png',
                b'\x89PNG\r\n\x1a\n' + b'\x00' * MAX_LOGO_BYTES,
                content_type='image/png',
            )),
        )
        for payload in payloads:
            with self.subTest(name=payload['logo'].name):
                response = self.client.post(
                    reverse('curriculum:appearance_save'), payload,
                )
                self.assertEqual(response.status_code, 400)

        self.assertFalse(AppearanceSettings.objects.exists())
        self.assertFalse((Path(self.media_root) / 'brand').exists())
