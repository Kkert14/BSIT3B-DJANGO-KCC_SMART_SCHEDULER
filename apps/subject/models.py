from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models


class Subject(models.Model):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=150)
    units = models.DecimalField(max_digits=3, decimal_places=1)
    lec_hours = models.PositiveSmallIntegerField(default=0)
    lab_hours = models.PositiveSmallIntegerField(default=0)
    program = models.ForeignKey(
        'program.Program',
        on_delete=models.RESTRICT,
        related_name='subjects',
    )
    academic_year = models.CharField(
        max_length=9,
        validators=[RegexValidator(r'^[0-9]{4}-[0-9]{4}$')],
    )
    year_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(6)]
    )
    semester = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(3)]
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
        unique_together = [['program', 'code', 'academic_year', 'semester']]
        ordering = ['program__code', 'code']

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def prerequisite_id_display(self):
        return self.prerequisite.id if self.prerequisite else ""
