from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

ACADEMIC_YEAR_CHOICES = [
    ('2023-2024', 'A.Y. 2023-2024'),
    ('2024-2025', 'A.Y. 2024-2025'),
    ('2025-2026', 'A.Y. 2025-2026'),
    ('2026-2027', 'A.Y. 2026-2027'),
    ('2027-2028', 'A.Y. 2027-2028'),
    ('2028-2029', 'A.Y. 2028-2029'),
]


class Curriculum(models.Model):
    """A curriculum plan for an academic year, shared by every program."""

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    academic_year = models.CharField(
        max_length=9,
        unique=True,
        choices=ACADEMIC_YEAR_CHOICES,
    )
    is_active = models.BooleanField(default=False)

    class Meta:
        db_table = 'curricula'
        ordering = ['-academic_year']
        verbose_name = 'Curriculum'
        verbose_name_plural = 'Curricula'

    def __str__(self):
        return f'A.Y. {self.academic_year}'

    def save(self, *args, **kwargs):
        """Only one curriculum may be active at a time."""
        self.code = self.academic_year
        self.name = f'Curriculum {self.academic_year}'
        if self.is_active:
            Curriculum.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class Semester(models.Model):
    """A semester within a curriculum (1st, 2nd or Summer)."""

    SEMESTER_CHOICES = [
        (1, 'Semester 1'),
        (2, 'Semester 2'),
        (3, 'Summer'),
    ]

    curriculum = models.ForeignKey(
        Curriculum,
        on_delete=models.CASCADE,
        related_name='semesters',
    )
    semester_number = models.PositiveSmallIntegerField(
        choices=SEMESTER_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(3)],
    )
    is_active = models.BooleanField(default=False)

    class Meta:
        db_table = 'semesters'
        unique_together = [['curriculum', 'semester_number']]
        ordering = ['curriculum', 'semester_number']
        verbose_name = 'Semester'
        verbose_name_plural = 'Semesters'

    def __str__(self):
        return f'A.Y. {self.curriculum.academic_year} — {self.get_semester_number_display()}'

    @property
    def short_label(self):
        """Compact label for tables and badges."""
        return {
            1: '1st Sem',
            2: '2nd Sem',
            3: 'Summer',
        }.get(self.semester_number, self.get_semester_number_display())

    def save(self, *args, **kwargs):
        """Only one semester may be active per curriculum at a time."""
        if self.is_active:
            Semester.objects.filter(curriculum=self.curriculum).exclude(
                pk=self.pk
            ).update(is_active=False)
        super().save(*args, **kwargs)
