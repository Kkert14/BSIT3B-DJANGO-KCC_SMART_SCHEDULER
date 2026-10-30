from django.db import models


MAJOR_CHOICES = [
    ('Software Development', 'Software Development'),
    ('Network Administration', 'Network Administration'),
    ('Information Systems', 'Information Systems'),
    ('Business Management', 'Business Management'),
    ('Financial Management', 'Financial Management'),
    ('Marketing Management', 'Marketing Management'),
    ('Management Accounting', 'Management Accounting'),
]


class Program(models.Model):
    program_code = models.CharField(max_length=20, unique=True)
    program_description = models.CharField(max_length=150, unique=True)
    major = models.CharField(
        max_length=100, blank=True, default='', choices=MAJOR_CHOICES
    )
    department = models.CharField(max_length=100, blank=True, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'programs'
        ordering = ['program_code']

    def __str__(self):
        return f"{self.program_code} — {self.program_description}"
