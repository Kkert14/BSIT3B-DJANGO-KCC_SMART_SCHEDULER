from django.contrib import admin

from .models import Building


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')
    list_editable = ('is_active',)
