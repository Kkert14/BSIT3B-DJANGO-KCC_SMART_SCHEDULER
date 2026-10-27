from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.curriculum.models import Semester
from apps.program.models import Program


class Section(models.Model):
    name = models.CharField(max_length=50)
    program = models.ForeignKey(
        Program,
        on_delete=models.RESTRICT,
        related_name='sections',
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.RESTRICT,
        related_name='sections',
    )
    year_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(6)]
    )
    capacity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'sections'
        unique_together = [['semester', 'program', 'year_level', 'name']]
        ordering = ['semester', 'program__code', 'year_level', 'name']

    def __str__(self):
        return self.name
