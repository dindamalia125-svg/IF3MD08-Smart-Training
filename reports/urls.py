from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.ekspor, name="ekspor"),
    path("unduh/", views.unduh, name="unduh"),
]
