from django.contrib import admin

from .models import Section


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'program', 'semester', 'year_level', 'capacity', 'is_active')
    list_filter = ('program', 'semester__curriculum__academic_year', 'semester', 'year_level', 'is_active')
    search_fields = ('name', 'program__program_code', 'program__program_description')
    raw_id_fields = ('program', 'semester')
