from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.curriculum.models import Semester


class Schedule(models.Model):
    CLASS_TYPE_CHOICES = [
        ('Lecture', 'Lecture'),
        ('Laboratory', 'Laboratory'),
    ]

    semester = models.ForeignKey(
        Semester,
        on_delete=models.RESTRICT,
        related_name='schedules',
    )
    teacher = models.ForeignKey(
        'faculty.Faculty',
        on_delete=models.RESTRICT,
        related_name='schedules',
    )
    subject = models.ForeignKey(
        'subject.Subject',
        on_delete=models.RESTRICT,
        related_name='schedules',
    )
    section = models.ForeignKey(
        'section.Section',
        on_delete=models.RESTRICT,
        related_name='schedules',
    )
    room = models.ForeignKey(
        'rooms.Room',
        on_delete=models.RESTRICT,
        related_name='schedules',
    )
    class_type = models.CharField(max_length=12, choices=CLASS_TYPE_CHOICES)
    day_of_week = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(7)]
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'schedules'
        unique_together = [
            ['teacher', 'semester', 'day_of_week', 'start_time'],
            ['room', 'semester', 'day_of_week', 'start_time'],
            ['section', 'semester', 'day_of_week', 'start_time'],
        ]
        ordering = ['semester', 'day_of_week', 'start_time']

    def __str__(self):
        return f"{self.subject.code} — {self.section} ({self.get_day_of_week_display()} {self.start_time})"
