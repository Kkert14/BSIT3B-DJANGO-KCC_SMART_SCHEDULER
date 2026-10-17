from django.contrib import admin

from .models import Section


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'program', 'year_level', 'academic_year', 'capacity', 'is_active')
    list_filter = ('program', 'year_level', 'academic_year', 'is_active')
    search_fields = ('name', 'program__code', 'program__name', 'academic_year')
    list_editable = ('is_active',)
    raw_id_fields = ('program',)
