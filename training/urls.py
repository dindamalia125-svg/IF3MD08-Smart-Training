from django.urls import path

from . import views

app_name = "training"

urlpatterns = [
    path("manpower/", views.manpower, name="manpower"),
    path("capaian/", views.capaian, name="capaian"),
    path("penelusuran/", views.penelusuran, name="penelusuran"),
    path("trainee/<int:pk>/", views.trainee_profil, name="trainee_profil"),
    path("trainee/<int:pk>/evaluasi/", views.evaluasi, name="evaluasi"),
    path("sertifikat/", views.sertifikat, name="sertifikat"),
    path("sertifikat/pdf/", views.sertifikat_pdf, name="sertifikat_pdf"),
]
