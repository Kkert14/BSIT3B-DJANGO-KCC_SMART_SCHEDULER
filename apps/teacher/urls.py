from django.urls import path
from . import views

app_name = 'teacher'

urlpatterns = [
    path('', views.teacher_list_page, name='teacher_list'),
    path('ajax/list/', views.teacher_list_ajax, name='teacher_list_ajax'),
    path('ajax/get/<int:pk>/', views.teacher_get_ajax, name='teacher_get_ajax'),
    path('ajax/save/', views.teacher_save_ajax, name='teacher_save_ajax'),
    path('ajax/delete/<int:pk>/', views.teacher_delete_ajax, name='teacher_delete_ajax'),
]
