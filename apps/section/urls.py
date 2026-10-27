from django.urls import path
from . import views

app_name = 'section'

urlpatterns = [
    path('', views.section_list_page, name='section_list'),
    path('ajax/list/', views.section_list_ajax, name='section_list_ajax'),
    path('ajax/get/<int:pk>/', views.section_get_ajax, name='section_get_ajax'),
    path('ajax/save/', views.section_save_ajax, name='section_save_ajax'),
    path('ajax/delete/<int:pk>/', views.section_delete_ajax, name='section_delete_ajax'),
    path('export/excel/', views.section_export_excel, name='section_export_excel'),
    path('import/excel/', views.section_import_excel, name='section_import_excel'),
]
