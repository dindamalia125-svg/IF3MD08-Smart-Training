from django.contrib import admin
from django.urls import include, path
from accounts.views import home

urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("master/", include("master.urls")),
    path("trainer/", include("training.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("laporan/", include("reports.urls")),
    path("manpower/", include("ai_parser.urls")),
]
