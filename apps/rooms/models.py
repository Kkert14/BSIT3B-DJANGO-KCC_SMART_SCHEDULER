from django.core.validators import MinValueValidator
from django.db import models


class Room(models.Model):
    ROOM_TYPE_CHOICES = [
        ('Classroom', 'Classroom'),
        ('Laboratory', 'Laboratory'),
        ('Lecture Hall', 'Lecture Hall'),
        ('Other', 'Other'),
    ]

    building = models.ForeignKey(
        'building.Building',
        on_delete=models.RESTRICT,
        related_name='rooms',
    )
    room_name = models.CharField(max_length=120)
    room_type = models.CharField(max_length=30, choices=ROOM_TYPE_CHOICES, default='Classroom')
    capacity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'rooms'
        unique_together = [['building', 'room_name']]
        ordering = ['building__code', 'room_name']

    def __str__(self):
        return self.room_name
