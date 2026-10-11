from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("masuk/", views.login_view, name="login"),
    path("keluar/", views.logout_view, name="logout"),
    path("pengguna/", views.user_list, name="user_list"),
    path("pengguna/tambah/", views.user_list, name="user_add"),
    path("pengguna/<int:pk>/ubah/", views.user_list, name="user_edit"),
    path("pengguna/<int:pk>/status/", views.user_toggle, name="user_toggle"),
    path("audit-log/", views.audit_log, name="audit_log"),
]
