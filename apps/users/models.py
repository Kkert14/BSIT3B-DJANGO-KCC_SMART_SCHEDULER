from django.conf import settings
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f'{self.user.username} ({self.get_role_display()})'

    @property
    def is_admin(self):
        return self.role == 'admin' or self.user.is_superuser

    @property
    def is_teacher(self):
        return self.role == 'teacher' or self.user.is_superuser

    @property
    def is_student(self):
        return self.role == 'student'


class LoginAttempt(models.Model):
    """Tracks failed sign-in attempts for a username.

    The counter lives in the database rather than the session, so clearing
    cookies, switching browsers or using a private window does not reset it.
    """

    username = models.CharField(max_length=150, unique=True)
    failed_count = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_attempt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'login_attempts'
        ordering = ['-last_attempt']
        verbose_name = 'Login Attempt'
        verbose_name_plural = 'Login Attempts'

    def __str__(self):
        return f'{self.username} ({self.failed_count} failed)'

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def seconds_remaining(self):
        """Seconds until the lock expires (0 when not locked)."""
        if not self.is_locked:
            return 0
        return int((self.locked_until - timezone.now()).total_seconds())
