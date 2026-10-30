from django.urls import path
from . import views

app_name = 'rooms'

urlpatterns = [
    path('', views.room_list_page, name='room_list'),
    path('ajax/list/', views.room_list_ajax, name='room_list_ajax'),
    path('ajax/get/<int:pk>/', views.room_get_ajax, name='room_get_ajax'),
    path('ajax/save/', views.room_save_ajax, name='room_save_ajax'),
    path('ajax/delete/<int:pk>/', views.room_delete_ajax, name='room_delete_ajax'),
]
