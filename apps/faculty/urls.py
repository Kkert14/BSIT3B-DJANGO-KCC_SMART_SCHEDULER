from django.urls import path

from . import views

app_name = 'faculty'
urlpatterns = [
    path('', views.faculty_list_page, name='faculty_list'),
    path('ajax/list/', views.faculty_list_ajax, name='faculty_list_ajax'),
    path('ajax/get/<int:pk>/', views.faculty_get_ajax, name='faculty_get_ajax'),
    path('ajax/save/', views.faculty_save_ajax, name='faculty_save_ajax'),
    path('ajax/delete/<int:pk>/', views.faculty_delete_ajax, name='faculty_delete_ajax'),
    path('export/excel/', views.faculty_export_excel, name='faculty_export_excel'),
    path('import/excel/', views.faculty_import_excel, name='faculty_import_excel'),
]
