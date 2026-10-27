from django.contrib import admin

from .models import Faculty


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ('employee_number', 'first_name', 'last_name', 'email', 'position', 'user', 'is_active')
    list_filter = ('is_active', 'position')
    search_fields = ('employee_number', 'first_name', 'last_name', 'email', 'user__username')
    list_editable = ('is_active',)
    raw_id_fields = ('user',)
