from django.db import models


class Program(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'programs'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} — {self.name}"
