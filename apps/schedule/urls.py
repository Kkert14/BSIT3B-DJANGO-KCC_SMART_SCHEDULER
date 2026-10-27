from django.urls import path
from . import views

app_name = 'schedule'

urlpatterns = [
    path('', views.schedule_list_page, name='schedule_list'),
    path('ajax/list/', views.schedule_list_ajax, name='schedule_list_ajax'),
    path('ajax/get/<int:pk>/', views.schedule_get_ajax, name='schedule_get_ajax'),
    path('ajax/save/', views.schedule_save_ajax, name='schedule_save_ajax'),
    path('ajax/delete/<int:pk>/', views.schedule_delete_ajax, name='schedule_delete_ajax'),
    path('export/excel/', views.schedule_export_excel, name='schedule_export_excel'),
    path('import/excel/', views.schedule_import_excel, name='schedule_import_excel'),
]
