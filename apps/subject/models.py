from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.curriculum.models import Semester
from apps.program.models import Program


class Subject(models.Model):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=150)
    units = models.DecimalField(max_digits=3, decimal_places=1)
    lec_hours = models.PositiveSmallIntegerField(default=0)
    lab_hours = models.PositiveSmallIntegerField(default=0)
    program = models.ForeignKey(
        Program,
        on_delete=models.RESTRICT,
        related_name='subjects',
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.RESTRICT,
        related_name='subjects',
    )
    year_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(6)]
    )
    prerequisite = models.ForeignKey(
        'self',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='dependents',
    )

    class Meta:
        db_table = 'subjects'
        unique_together = [['program', 'code', 'semester']]
        ordering = ['program__program_code', 'code']

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def total_weekly_hours(self):
        """Total contact hours per week (Lecture + Laboratory)."""
        return (self.lec_hours or 0) + (self.lab_hours or 0)

    @property
    def prerequisite_id_display(self):
        return self.prerequisite.id if self.prerequisite else ""
