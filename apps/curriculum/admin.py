from django.contrib import admin

from .models import Curriculum, Semester


@admin.register(Curriculum)
class CurriculumAdmin(admin.ModelAdmin):
    list_display = ('academic_year', 'is_active')
    list_filter = ('academic_year', 'is_active')
    search_fields = ('academic_year',)


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ('curriculum', 'semester_number', 'is_active')
    list_filter = ('curriculum', 'semester_number', 'is_active')
    search_fields = ('curriculum__academic_year',)
    raw_id_fields = ('curriculum',)
