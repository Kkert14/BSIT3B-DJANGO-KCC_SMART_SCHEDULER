from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models


class Section(models.Model):
    name = models.CharField(max_length=50)
    program = models.ForeignKey(
        'program.Program',
        on_delete=models.RESTRICT,
        related_name='sections',
    )
    year_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(6)]
    )
    academic_year = models.CharField(
        max_length=9,
        validators=[RegexValidator(r'^[0-9]{4}-[0-9]{4}$')],
    )
    capacity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'sections'
        unique_together = [['academic_year', 'program', 'year_level', 'name']]
        ordering = ['academic_year', 'program__code', 'year_level', 'name']

    def __str__(self):
        return self.name
