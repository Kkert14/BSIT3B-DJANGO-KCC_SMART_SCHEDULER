from django.contrib import admin

from .models import Program


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ('program_code', 'program_description', 'major', 'department', 'is_active')
    list_filter = ('is_active', 'department')
    search_fields = ('program_code', 'program_description', 'major', 'department')
    list_editable = ('is_active',)
