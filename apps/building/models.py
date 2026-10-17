from django.db import models


class Building(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'buildings'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} — {self.name}"
