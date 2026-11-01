from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("admin/", views.super_admin, name="super_admin"),
    path("trainer/", views.trainer, name="trainer"),
]
