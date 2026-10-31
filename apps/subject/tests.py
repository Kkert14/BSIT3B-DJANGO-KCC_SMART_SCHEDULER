"""Tests for course hours in the program course page's save endpoint."""

import json

from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.curriculum.models import Curriculum, Semester
from apps.program.models import Program
from apps.users.models import UserProfile

from .models import Subject
from .views import subject_save_ajax

User = get_user_model()


class SubjectHoursTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.curriculum = Curriculum.objects.create(
            academic_year='2025-2026', is_active=True,
        )
        cls.semester = Semester.objects.create(
            curriculum=cls.curriculum, semester_number=1, is_active=True,
        )
        cls.program = Program.objects.create(
            program_code='BSIT', program_description='BS Information Technology',
        )
        cls.admin = User.objects.create_user(username='hours_admin', password='test-pass-123')
        profile, _ = UserProfile.objects.get_or_create(
            user=cls.admin, defaults={'role': 'admin'},
        )
        profile.role = 'admin'
        profile.save()
        cls.admin._state.fields_cache.pop('profile', None)

    def save(self, **overrides):
        data = {
            'program': self.program.id,
            'code': 'IT201',
            'name': 'Data Structures',
            'units': '3',
            'semester': self.semester.id,
            'year_level': '2',
            'lecture_hours': '2',
            'lab_hours': '1',
        }
        data.update(overrides)
        request = RequestFactory().post(reverse('subject:subject_save_ajax'), data)
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        MessageMiddleware(lambda r: None).process_request(request)
        request.user = self.admin
        return subject_save_ajax(request)

    def test_total_hours_is_the_sum_of_lecture_and_lab(self):
        response = self.save()
        self.assertEqual(response.status_code, 200)
        subject = Subject.objects.get(code='IT201')
        self.assertEqual(subject.lecture_hours, 2)
        self.assertEqual(subject.lab_hours, 1)
        self.assertEqual(subject.total_hours, 3)

    def test_lecture_only_course_is_allowed(self):
        response = self.save(lab_hours='0')
        self.assertEqual(response.status_code, 200)
        subject = Subject.objects.get(code='IT201')
        self.assertEqual(subject.lecture_hours, 2)
        self.assertEqual(subject.lab_hours, 0)

    def test_lab_only_course_is_allowed(self):
        response = self.save(lecture_hours='0', lab_hours='4')
        self.assertEqual(response.status_code, 200)
        subject = Subject.objects.get(code='IT201')
        self.assertEqual(subject.lecture_hours, 0)
        self.assertEqual(subject.lab_hours, 4)

    def test_a_course_needs_some_hours(self):
        response = self.save(lecture_hours='0', lab_hours='0')
        self.assertEqual(response.status_code, 400)
        self.assertIn('lecture or lab hours', json.loads(response.content)['error'])
        self.assertFalse(Subject.objects.filter(code='IT201').exists())
