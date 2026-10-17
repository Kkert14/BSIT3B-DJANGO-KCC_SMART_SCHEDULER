from django.contrib import admin

from .models import Room


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('room_name', 'building', 'room_type', 'capacity', 'is_active')
    list_filter = ('building', 'room_type', 'is_active')
    search_fields = ('room_name', 'building__code', 'building__name')
    list_editable = ('is_active',)
