from django.urls import path
from . import views

app_name = "ai_parser"

urlpatterns = [
    path("", views.manpower_list, name="manpower_list"),
    path("upload/", views.upload_document, name="upload_document"),
    path("preview/", views.preview_import, name="preview_import"),
    path("confirm/", views.confirm_import, name="confirm_import"),
    path("<int:pk>/assignment/", views.update_assignment, name="update_assignment"),
    path("<int:pk>/", views.manpower_profile, name="manpower_profile"),
]
