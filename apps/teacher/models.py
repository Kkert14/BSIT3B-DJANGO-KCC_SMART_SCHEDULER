from django.conf import settings
from django.db import models


class Teacher(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teacher_profile',
    )
    employee_number = models.CharField(max_length=30, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=30, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'teachers'
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.employee_number})"

    @property
    def user_id_display(self):
        return self.user.id if self.user else ""

