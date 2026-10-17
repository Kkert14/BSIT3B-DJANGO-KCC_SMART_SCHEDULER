from django.contrib import admin

from .models import Schedule


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = (
        'subject', 'section', 'teacher', 'room', 'academic_year', 'semester',
        'class_type', 'day_of_week', 'start_time', 'end_time',
    )
    list_filter = ('academic_year', 'semester', 'class_type', 'day_of_week')
    search_fields = (
        'subject__code', 'subject__name', 'section__name',
        'teacher__first_name', 'teacher__last_name', 'room__room_name',
    )
    raw_id_fields = ('teacher', 'subject', 'section', 'room')
