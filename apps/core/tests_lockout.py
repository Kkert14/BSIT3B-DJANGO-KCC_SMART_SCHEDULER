"""Tests for the sign-in lockout.

The lockout counter is kept in the database, so these tests use a fresh
``Client`` (with no session cookie) to prove that clearing cookies does not
reset the counter.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.users.models import LoginAttempt

User = get_user_model()

PASSWORD = 'correct-horse-battery'


class LoginLockoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='lockout_user', password=PASSWORD, is_superuser=True
        )
        self.url = reverse('login')

    def _post(self, client, username, password):
        return client.post(
            self.url,
            {'username': username, 'password': password},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

    def test_successful_login_clears_the_counter(self):
        client = Client()
        for _ in range(3):
            self._post(client, 'lockout_user', 'wrong')

        self.assertEqual(
            LoginAttempt.objects.get(username='lockout_user').failed_count, 3
        )

        response = self._post(client, 'lockout_user', PASSWORD)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(LoginAttempt.objects.filter(username='lockout_user').exists())

    def test_account_is_locked_after_five_failures(self):
        client = Client()
        for _ in range(5):
            self._post(client, 'lockout_user', 'wrong')

        attempt = LoginAttempt.objects.get(username='lockout_user')
        self.assertEqual(attempt.failed_count, 5)
        self.assertTrue(attempt.is_locked)
        self.assertGreater(attempt.seconds_remaining(), 0)

    def test_lockout_survives_a_new_session(self):
        """Clearing cookies must not reset the counter."""
        first = Client()
        for _ in range(5):
            self._post(first, 'lockout_user', 'wrong')

        # A brand new client has no session cookie at all.
        second = Client()
        response = self._post(second, 'lockout_user', PASSWORD)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', second.session)
        # The correct password is still refused while the account is locked.
        self.assertTrue(
            LoginAttempt.objects.get(username='lockout_user').is_locked
        )

    def test_lockout_is_tracked_per_username(self):
        client = Client()
        for _ in range(5):
            self._post(client, 'lockout_user', 'wrong')

        other = Client()
        response = self._post(other, 'someone_else', PASSWORD)
        self.assertEqual(response.status_code, 200)

        # A different account is unaffected by the lock on lockout_user.
        other_attempt = LoginAttempt.objects.get(username='someone_else')
        self.assertFalse(other_attempt.is_locked)
        self.assertEqual(other_attempt.failed_count, 1)
        self.assertTrue(
            LoginAttempt.objects.get(username='lockout_user').is_locked
        )

    def test_lock_expires_and_the_account_works_again(self):
        client = Client()
        for _ in range(5):
            self._post(client, 'lockout_user', 'wrong')

        attempt = LoginAttempt.objects.get(username='lockout_user')
        # Pretend the lock was set an hour ago.
        from django.utils import timezone
        attempt.locked_until = timezone.now() - timezone.timedelta(hours=1)
        attempt.save()

        response = self._post(client, 'lockout_user', PASSWORD)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))
        self.assertFalse(LoginAttempt.objects.filter(username='lockout_user').exists())
