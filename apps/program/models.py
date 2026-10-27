from django.db import models


class Program(models.Model):
    program_code = models.CharField(max_length=20, unique=True)
    program_description = models.CharField(max_length=150, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'programs'
        ordering = ['program_code']

    def __str__(self):
        return f"{self.program_code} — {self.program_description}"
