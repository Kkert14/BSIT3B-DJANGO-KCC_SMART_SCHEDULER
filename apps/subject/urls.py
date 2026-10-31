from django.urls import path
from . import views

app_name = 'subject'

urlpatterns = [
    path('', views.subject_list_page, name='subject_list'),
    path('ajax/save/', views.subject_save_ajax, name='subject_save_ajax'),
    path('ajax/delete/<int:pk>/', views.subject_delete_ajax, name='subject_delete_ajax'),
]
