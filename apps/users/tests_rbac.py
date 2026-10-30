"""Tests for role-based access control across the Smart Scheduler apps.

The views are resolved from their URL and called directly instead of going
through the Django test client. The test client copies the template context on
every render, which is broken on Python 3.14 with Django 5.0
(``django.template.context.BaseContext.__copy__``). Calling the view directly
exercises the same decorator chain without that machinery.
"""

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.urls import resolve, reverse

from apps.building.models import Building
from apps.users.models import UserProfile

User = get_user_model()

# Every endpoint that mutates data.
WRITE_ENDPOINTS = [
    'building:building_save_ajax',
    'building:building_delete_ajax',
    'building:building_import_excel',
    'program:program_save_ajax',
    'program:program_delete_ajax',
    'program:program_import_excel',
    'rooms:room_save_ajax',
    'rooms:room_delete_ajax',
    'rooms:room_import_excel',
    'schedule:schedule_save_ajax',
    'schedule:schedule_delete_ajax',
    'schedule:schedule_import_excel',
    'section:section_save_ajax',
    'section:section_delete_ajax',
    'section:section_import_excel',
    'subject:subject_save_ajax',
    'subject:subject_delete_ajax',
    'subject:subject_import_excel',
    'faculty:faculty_save_ajax',
    'faculty:faculty_delete_ajax',
    'faculty:faculty_import_excel',
    'users:user_save_ajax',
    'users:user_delete_ajax',
    'users:user_import_excel',
]

EXPORT_ENDPOINTS = [
    'building:building_export_excel',
    'program:program_export_excel',
    'rooms:room_export_excel',
    'schedule:schedule_export_excel',
    'section:section_export_excel',
    'subject:subject_export_excel',
    'faculty:faculty_export_excel',
    'users:user_export_excel',
]

# Pages every signed-in user may read.
READ_PAGES = [
    'building:building_list',
    'program:program_list',
    'rooms:room_list',
    'schedule:schedule_list',
    'section:section_list',
    'faculty:faculty_list',
]

# A pk that does not exist, so "allowed" requests reach the view and 404
# instead of mutating real rows.
MISSING_PK = 999999


class RoleTestMixin:
    """Helpers to build requests for a user with a given role."""

    def make_user(self, username, role, is_superuser=False):
        user = User.objects.create_user(username=username, password='test-pass-123')
        if is_superuser:
            user.is_superuser = True
            user.is_staff = True
            user.save()
        profile, _ = UserProfile.objects.get_or_create(
            user=user, defaults={'role': role}
        )
        profile.role = role
        profile.save()
        # The one-to-one descriptor caches the profile on the user instance
        # when the profile is first created, so drop the stale copy.
        user._state.fields_cache.pop('profile', None)
        return user

    def build_request(self, user, method, url_name, pk=None, data=None):
        """Return a request wired up with session, messages and a user."""
        factory = RequestFactory()
        if url_name is not None:
            url = reverse(url_name, args=[pk]) if pk is not None else reverse(url_name)
        else:
            url = '/'
        request = getattr(factory, method)(url, data or {})

        # The messages middleware needs a session to store the message.
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        MessageMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)

        request.user = user
        return request

    def call(self, user, method, url_name, pk=None, data=None):
        """Resolve the view for ``url_name`` and invoke it.

        Returns the response, or ``None`` when the view raised ``Http404``
        (which happens outside the normal middleware stack).
        """
        request = self.build_request(user, method, url_name, pk=pk, data=data)
        match = resolve(request.path)
        try:
            return match.func(request, **match.kwargs)
        except Http404:
            return None

    def reached_view(self, user, method, url_name, pk=None, data=None):
        """True when the request was NOT blocked by the role decorator."""
        request = self.build_request(user, method, url_name, pk=pk, data=data)
        match = resolve(request.path)
        try:
            response = match.func(request, **match.kwargs)
        except Http404:
            return True
        return response.status_code != 403

    def pk_for(self, url_name):
        """The pk argument a delete endpoint needs, if any."""
        return MISSING_PK if 'delete' in url_name else None


class WriteEndpointAccessTests(RoleTestMixin, TestCase):
    """Non-admin roles must not be able to mutate data."""

    def setUp(self):
        self.student = self.make_user('rbac_student', 'student')
        self.teacher = self.make_user('rbac_teacher', 'teacher')
        self.admin = self.make_user('rbac_admin', 'admin')
        self.building = Building.objects.create(code='RBAC_B1', name='RBAC Building 1')

    def test_student_is_denied_on_every_write_endpoint(self):
        for url_name in WRITE_ENDPOINTS:
            with self.subTest(endpoint=url_name):
                response = self.call(
                    self.student, 'post', url_name, pk=self.pk_for(url_name)
                )
                self.assertEqual(
                    response.status_code, 403,
                    f'{url_name} should return 403 for a student',
                )
                body = json.loads(response.content)
                self.assertIn('error', body)
                self.assertIn('permission', body['error'].lower())

    def test_teacher_is_denied_on_every_write_endpoint(self):
        for url_name in WRITE_ENDPOINTS:
            with self.subTest(endpoint=url_name):
                response = self.call(
                    self.teacher, 'post', url_name, pk=self.pk_for(url_name)
                )
                self.assertEqual(
                    response.status_code, 403,
                    f'{url_name} should return 403 for a teacher',
                )
                body = json.loads(response.content)
                self.assertIn('error', body)

    def test_admin_is_allowed_on_every_write_endpoint(self):
        """Admin reaches the view logic (not blocked by the decorator)."""
        for url_name in WRITE_ENDPOINTS:
            with self.subTest(endpoint=url_name):
                self.assertTrue(
                    self.reached_view(
                        self.admin, 'post', url_name, pk=self.pk_for(url_name)
                    ),
                    f'{url_name} should not be blocked for an admin',
                )

    def test_student_cannot_delete_a_building(self):
        """The exact escalation found during the audit."""
        response = self.call(
            self.student, 'post', 'building:building_delete_ajax',
            pk=self.building.id,
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            Building.objects.filter(pk=self.building.id).exists(),
            'The building must not be deleted by a student.',
        )

    def test_student_cannot_create_a_building(self):
        response = self.call(
            self.student, 'post', 'building:building_save_ajax',
            data={'code': 'RBAC_NEW', 'name': 'RBAC New Building'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Building.objects.filter(code='RBAC_NEW').exists())


class ExportAccessTests(RoleTestMixin, TestCase):
    """Exports are admin-only and redirect browsers back to the dashboard."""

    def setUp(self):
        self.student = self.make_user('rbac_export_student', 'student')
        self.admin = self.make_user('rbac_export_admin', 'admin')

    def test_student_is_redirected_away_from_every_export(self):
        for url_name in EXPORT_ENDPOINTS:
            with self.subTest(endpoint=url_name):
                response = self.call(self.student, 'get', url_name)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, reverse('dashboard'))

    def test_admin_can_export(self):
        for url_name in EXPORT_ENDPOINTS:
            with self.subTest(endpoint=url_name):
                response = self.call(self.admin, 'get', url_name)
                self.assertEqual(response.status_code, 200)


class ReadAccessTests(RoleTestMixin, TestCase):
    """Every signed-in role keeps read access to the list pages."""

    def setUp(self):
        self.student = self.make_user('rbac_read_student', 'student')
        self.teacher = self.make_user('rbac_read_teacher', 'teacher')
        self.admin = self.make_user('rbac_read_admin', 'admin')

    def test_all_roles_can_read_list_pages(self):
        for user in (self.student, self.teacher, self.admin):
            for url_name in READ_PAGES:
                with self.subTest(endpoint=url_name, role=user.username):
                    response = self.call(user, 'get', url_name)
                    self.assertEqual(response.status_code, 200)

    def test_anonymous_users_are_redirected_to_login(self):
        for url_name in READ_PAGES:
            with self.subTest(endpoint=url_name):
                response = self.call(AnonymousUser(), 'get', url_name)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('login'), response.url)

    def test_retired_pages_redirect_to_programs_tabs(self):
        """Curriculum and Courses now live as tabs on the Programs page."""
        cases = [
            ('curriculum:curriculum_list', '?tab=curriculum'),
            ('subject:subject_list', '?tab=courses'),
        ]
        for url_name, suffix in cases:
            with self.subTest(endpoint=url_name):
                response = self.call(self.admin, 'get', url_name)
                self.assertEqual(response.status_code, 302)
                self.assertIn(
                    reverse('program:program_list') + suffix, response.url
                )

    def test_programs_hub_tabs_are_readable(self):
        for tab in ('programs', 'courses'):
            with self.subTest(tab=tab):
                response = self.call(
                    self.student, 'get', 'program:program_list',
                    data={'tab': tab},
                )
                self.assertEqual(response.status_code, 200)
        response = self.call(
            self.admin, 'get', 'program:program_list',
            data={'tab': 'curriculum'},
        )
        self.assertEqual(response.status_code, 200)

    def test_curriculum_tab_stays_admin_only(self):
        response = self.call(
            self.student, 'get', 'program:program_list',
            data={'tab': 'curriculum'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    def test_admin_only_pages_are_closed_to_students(self):
        response = self.call(self.student, 'get', 'users:user_list')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    def test_admin_only_pages_are_open_to_admins(self):
        response = self.call(self.admin, 'get', 'users:user_list')
        self.assertEqual(response.status_code, 200)


class SuperuserTests(RoleTestMixin, TestCase):
    """Superusers bypass role checks entirely."""

    def setUp(self):
        self.superuser = self.make_user('rbac_super', 'student', is_superuser=True)

    def test_superuser_is_not_blocked_on_write_endpoints(self):
        for url_name in WRITE_ENDPOINTS:
            with self.subTest(endpoint=url_name):
                self.assertTrue(
                    self.reached_view(
                        self.superuser, 'post', url_name, pk=self.pk_for(url_name)
                    ),
                    f'{url_name} should not be blocked for a superuser',
                )


class TemplateGatingTests(RoleTestMixin, TestCase):
    """Write controls are hidden from non-admins in the rendered HTML."""

    def setUp(self):
        self.student = self.make_user('rbac_tmpl_student', 'student')
        self.admin = self.make_user('rbac_tmpl_admin', 'admin')

    def test_admin_sees_the_add_button(self):
        response = self.call(self.admin, 'get', 'building:building_list')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-mode="create"', response.content)

    def test_student_does_not_see_the_add_button(self):
        response = self.call(self.student, 'get', 'building:building_list')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'data-mode="create"', response.content)

    def test_student_does_not_see_export_or_import_buttons(self):
        response = self.call(self.student, 'get', 'building:building_list')
        # The button markup, not the JavaScript that references these URLs.
        self.assertNotIn(b'export/excel/', response.content)
        self.assertNotIn(b'data-bs-target="#buildingImportModal"', response.content)

    def test_admin_sees_export_and_import_buttons(self):
        response = self.call(self.admin, 'get', 'building:building_list')
        self.assertIn(b'export/excel/', response.content)
        self.assertIn(b'data-bs-target="#buildingImportModal"', response.content)

    def test_student_does_not_see_the_actions_column(self):
        response = self.call(self.student, 'get', 'building:building_list')
        self.assertNotIn(b'<th class="w-1">Actions</th>', response.content)

    def test_student_does_not_see_the_users_nav_link(self):
        response = self.call(self.student, 'get', 'building:building_list')
        self.assertNotIn(b'fa-users"></i>Users', response.content)

    def test_admin_sees_the_users_nav_link(self):
        response = self.call(self.admin, 'get', 'building:building_list')
        self.assertIn(b'fa-users"></i>Users', response.content)


class RoleHelperTests(TestCase):
    """Unit tests for the role lookup helpers."""

    def setUp(self):
        self.student = self.make_user('rbac_h_student', 'student')
        self.teacher = self.make_user('rbac_h_teacher', 'teacher')
        self.admin = self.make_user('rbac_h_admin', 'admin')
        self.superuser = self.make_user('rbac_h_super', 'student', is_superuser=True)

    def make_user(self, username, role, is_superuser=False):
        user = User.objects.create_user(username=username, password='test-pass-123')
        if is_superuser:
            user.is_superuser = True
            user.save()
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={'role': role})
        profile.role = role
        profile.save()
        user._state.fields_cache.pop('profile', None)
        return user

    def test_get_user_role(self):
        from apps.users.decorators import get_user_role
        self.assertEqual(get_user_role(self.student), 'student')
        self.assertEqual(get_user_role(self.teacher), 'teacher')
        self.assertEqual(get_user_role(self.admin), 'admin')
        self.assertEqual(get_user_role(self.superuser), 'admin')

    def test_is_admin_is_teacher_is_student(self):
        from apps.users.decorators import is_admin, is_teacher, is_student
        self.assertTrue(is_admin(self.admin))
        self.assertTrue(is_admin(self.superuser))
        self.assertFalse(is_admin(self.teacher))
        self.assertFalse(is_admin(self.student))

        self.assertTrue(is_teacher(self.teacher))
        self.assertTrue(is_teacher(self.admin))
        self.assertTrue(is_teacher(self.superuser))
        self.assertFalse(is_teacher(self.student))

        self.assertTrue(is_student(self.student))
        self.assertFalse(is_student(self.teacher))
        self.assertFalse(is_student(self.admin))
        self.assertFalse(is_student(self.superuser))

    def test_user_without_profile_defaults_to_student(self):
        from apps.users.decorators import get_user_role
        orphan = User.objects.create_user(username='rbac_orphan', password='test-pass-123')
        UserProfile.objects.filter(user=orphan).delete()
        self.assertEqual(get_user_role(orphan), 'student')
