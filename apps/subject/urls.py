from django.urls import path
from . import views

app_name = 'subject'

urlpatterns = [
    path('', views.subject_list_page, name='subject_list'),
    path('ajax/list/', views.subject_list_ajax, name='subject_list_ajax'),
    path('ajax/get/<int:pk>/', views.subject_get_ajax, name='subject_get_ajax'),
    path('ajax/save/', views.subject_save_ajax, name='subject_save_ajax'),
    path('ajax/delete/<int:pk>/', views.subject_delete_ajax, name='subject_delete_ajax'),
    path('export/excel/', views.subject_export_excel, name='subject_export_excel'),
    path('import/excel/', views.subject_import_excel, name='subject_import_excel'),
]
