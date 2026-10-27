from django.urls import path

from . import views

app_name = 'curriculum'
urlpatterns = [
    path('', views.curriculum_list, name='curriculum_list'),
    path(
        'semester/<int:semester_id>/activate/',
        views.set_active_semester,
        name='set_active_semester',
    ),
]
