from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.program.models import Program


class Curriculum(models.Model):
    """A curriculum plan tied to a program and academic year.

    Example: BSIT-2024, "Bachelor of Science in Information Technology"
    for the 2024-2025 academic year.
    """

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    program = models.ForeignKey(
        Program,
        on_delete=models.RESTRICT,
        related_name='curricula',
    )
    academic_year = models.CharField(max_length=9)
    is_active = models.BooleanField(default=False)

    class Meta:
        db_table = 'curricula'
        ordering = ['-academic_year', 'code']
        unique_together = [['program', 'academic_year']]
        verbose_name = 'Curriculum'
        verbose_name_plural = 'Curricula'

    def __str__(self):
        return f'{self.code} — {self.name} ({self.academic_year})'

    def save(self, *args, **kwargs):
        """Only one curriculum may be active at a time."""
        if self.is_active:
            Curriculum.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class Semester(models.Model):
    """A semester within a curriculum (1st or 2nd semester)."""

    curriculum = models.ForeignKey(
        Curriculum,
        on_delete=models.CASCADE,
        related_name='semesters',
    )
    semester_number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(2)]
    )
    is_active = models.BooleanField(default=False)

    class Meta:
        db_table = 'semesters'
        unique_together = [['curriculum', 'semester_number']]
        ordering = ['curriculum', 'semester_number']
        verbose_name = 'Semester'
        verbose_name_plural = 'Semesters'

    def __str__(self):
        return f'{self.curriculum.code} — Semester {self.semester_number}'

    def save(self, *args, **kwargs):
        """Only one semester may be active per curriculum at a time."""
        if self.is_active:
            Semester.objects.filter(curriculum=self.curriculum).exclude(
                pk=self.pk
            ).update(is_active=False)
        super().save(*args, **kwargs)
