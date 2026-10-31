from django.urls import path
from . import views

app_name = 'program'

urlpatterns = [
    path('', views.program_list_page, name='program_list'),
    path('ajax/list/', views.program_list_ajax, name='program_list_ajax'),
    path('ajax/get/<int:pk>/', views.program_get_ajax, name='program_get_ajax'),
    path('<int:pk>/courses/', views.program_courses_page, name='program_courses'),
    path('ajax/save/', views.program_save_ajax, name='program_save_ajax'),
    path('ajax/delete/<int:pk>/', views.program_delete_ajax, name='program_delete_ajax'),
]
