from django.urls import path
from . import views

app_name = 'section'

urlpatterns = [
    path('', views.section_list_page, name='section_list'),
    path('ajax/list/', views.section_list_ajax, name='section_list_ajax'),
    path('ajax/get/<int:pk>/', views.section_get_ajax, name='section_get_ajax'),
    path('ajax/save/', views.section_save_ajax, name='section_save_ajax'),
    path('ajax/delete/<int:pk>/', views.section_delete_ajax, name='section_delete_ajax'),
]
