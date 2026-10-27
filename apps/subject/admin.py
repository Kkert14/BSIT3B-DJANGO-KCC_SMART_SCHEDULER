from django.contrib import admin

from .models import Subject


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'program', 'semester', 'year_level', 'units')
    list_filter = ('program', 'semester__curriculum__academic_year', 'semester', 'year_level')
    search_fields = ('code', 'name', 'program__code')
    raw_id_fields = ('program', 'prerequisite', 'semester')
