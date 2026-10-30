from django.urls import path
from . import views

app_name = 'schedule'

urlpatterns = [
    path('', views.schedule_list_page, name='schedule_list'),
    path('reports/', views.schedule_reports, name='schedule_reports'),
    path('reports/export/', views.schedule_reports_export, name='schedule_reports_export'),
    path('ajax/list/', views.schedule_list_ajax, name='schedule_list_ajax'),
    path('ajax/get/<int:pk>/', views.schedule_get_ajax, name='schedule_get_ajax'),
    path('ajax/save/', views.schedule_save_ajax, name='schedule_save_ajax'),
    path('ajax/batch-save/', views.schedule_batch_save_ajax, name='schedule_batch_save_ajax'),
    path('ajax/delete/<int:pk>/', views.schedule_delete_ajax, name='schedule_delete_ajax'),
]
