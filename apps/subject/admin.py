from django.contrib import admin

from .models import Subject


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'program', 'year_level', 'semester', 'units')
    list_filter = ('program', 'academic_year', 'year_level', 'semester')
    search_fields = ('code', 'name', 'program__code')
    raw_id_fields = ('program', 'prerequisite')
