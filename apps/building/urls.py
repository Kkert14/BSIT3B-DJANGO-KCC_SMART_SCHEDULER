from django.urls import path
from . import views

app_name = 'building'

urlpatterns = [
    path('', views.building_list_page, name='building_list'),
    path('ajax/list/', views.building_list_ajax, name='building_list_ajax'),
    path('ajax/get/<int:pk>/', views.building_get_ajax, name='building_get_ajax'),
    path('ajax/save/', views.building_save_ajax, name='building_save_ajax'),
    path('ajax/delete/<int:pk>/', views.building_delete_ajax, name='building_delete_ajax'),
]
