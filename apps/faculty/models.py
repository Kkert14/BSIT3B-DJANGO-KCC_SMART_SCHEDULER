from django.conf import settings
from django.db import models


class Faculty(models.Model):
    """Faculty member (formerly Teacher)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='faculty_profile',
    )
    employee_number = models.CharField(max_length=30, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=150, blank=True, default='')
    position = models.CharField(max_length=100, blank=True, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'faculty'
        ordering = ['last_name', 'first_name']
        verbose_name = 'Faculty'
        verbose_name_plural = 'Faculty'

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.employee_number})"

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    @property
    def user_id_display(self):
        return self.user.id if self.user else ""
