from django.urls import path
from . import views

app_name = 'program'

urlpatterns = [
    path('', views.program_list_page, name='program_list'),
    path('ajax/list/', views.program_list_ajax, name='program_list_ajax'),
    path('ajax/get/<int:pk>/', views.program_get_ajax, name='program_get_ajax'),
    path(
        'ajax/<int:pk>/courses/',
        views.program_courses_ajax,
        name='program_courses_ajax',
    ),
    path('ajax/save/', views.program_save_ajax, name='program_save_ajax'),
    path('ajax/delete/<int:pk>/', views.program_delete_ajax, name='program_delete_ajax'),
    path('export/excel/', views.program_export_excel, name='program_export_excel'),
    path('import/excel/', views.program_import_excel, name='program_import_excel'),
]
