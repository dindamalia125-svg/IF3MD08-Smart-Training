from django.urls import path

from . import views

app_name = "master"

urlpatterns = [
    path("proses/", views.proses_list, name="proses_list"),
    path("proses/tambah/", views.proses_list, name="proses_add"),
    path("proses/<int:pk>/ubah/", views.proses_list, name="proses_edit"),
    path("proses/<int:pk>/hapus/", views.proses_delete, name="proses_delete"),
    path("shift-lini/", views.shift_lini, name="shift_lini"),
    path("shift/<int:pk>/hapus/", views.shift_delete, name="shift_delete"),
    path("lini/<int:pk>/hapus/", views.lini_delete, name="lini_delete"),
]
