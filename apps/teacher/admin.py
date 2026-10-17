from django.contrib import admin

from .models import Teacher


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('employee_number', 'first_name', 'last_name', 'user', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('employee_number', 'first_name', 'last_name', 'user__username')
    list_editable = ('is_active',)
    raw_id_fields = ('user',)
