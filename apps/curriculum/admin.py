from django.contrib import admin

from .models import Curriculum, Semester


@admin.register(Curriculum)
class CurriculumAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'program', 'academic_year', 'is_active')
    list_filter = ('program', 'academic_year', 'is_active')
    search_fields = ('code', 'name', 'program__program_code')
    raw_id_fields = ('program',)


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ('curriculum', 'semester_number', 'is_active')
    list_filter = ('curriculum', 'semester_number', 'is_active')
    search_fields = ('curriculum__code', 'curriculum__name')
    raw_id_fields = ('curriculum',)
