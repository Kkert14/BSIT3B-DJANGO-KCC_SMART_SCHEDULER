from django.contrib import admin

from .models import Program


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ('program_code', 'program_description', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('program_code', 'program_description')
    list_editable = ('is_active',)
