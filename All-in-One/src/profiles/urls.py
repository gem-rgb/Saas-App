from django.urls import path
from . import views

urlpatterns = [
    path("", views.profile_list_view, name="profile_list"),
    path("edit/", views.profile_edit_view, name="profile_edit"),
    path("<str:username>/", views.profile_detail_view, name="profile_detail"),
]
