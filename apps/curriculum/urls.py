from django.urls import path

from . import views

app_name = 'curriculum'
urlpatterns = [
    path('', views.curriculum_list, name='curriculum_list'),
    path('ajax/save/', views.curriculum_save_ajax, name='curriculum_save_ajax'),
    path('ajax/delete/<int:pk>/', views.curriculum_delete_ajax, name='curriculum_delete_ajax'),
    path('semester/ajax/save/', views.semester_save_ajax, name='semester_save_ajax'),
    path('semester/ajax/delete/<int:pk>/', views.semester_delete_ajax, name='semester_delete_ajax'),
    path(
        'semester/<int:semester_id>/activate/',
        views.set_active_semester,
        name='set_active_semester',
    ),
]
