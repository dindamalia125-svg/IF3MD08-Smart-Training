from django.urls import reverse

from django.utils import timezone

SUPER_ADMIN_NAV = [
    ("Dashboard", "dashboard:super_admin", "/dashboard/admin/"),
    ("Manajemen Pengguna", "accounts:user_list", "/pengguna/"),
    ("Master Proses", "master:proses_list", "/master/proses/"),
    ("Master Shift & Lini", "master:shift_lini", "/master/shift-lini/"),
    ("Audit Log", "accounts:audit_log", "/audit-log/"),
]
TRAINER_NAV = [
    ("Dashboard", "dashboard:trainer", "/dashboard/trainer/"),
    ("Input Manpower (AI)", "training:manpower", "/trainer/manpower/"),
    ("Input Capaian", "training:capaian", "/trainer/capaian/"),
    ("Penelusuran Trainee", "training:penelusuran", "/trainer/penelusuran/"),
    ("Sertifikat", "training:sertifikat", "/trainer/sertifikat/"),
    ("Laporan", "reports:ekspor", "/laporan/"),
]


def navigation(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    items = SUPER_ADMIN_NAV if user.is_super_admin else TRAINER_NAV
    path = request.path
    nav = []
    for label, name, prefix in items:
        # Dashboard dan menu lain dianggap aktif bila path diawali prefix; trainee/profil dianggap "Penelusuran".
        active = path.startswith(prefix)
        if prefix == "/trainer/penelusuran/" and path.startswith("/trainer/trainee/") and "evaluasi" not in path:
            active = True
        if prefix == "/trainer/sertifikat/" and "evaluasi" in path:
            active = True
        nav.append({"label": label, "url": reverse(name), "active": active})
    return {"nav_items": nav, "now": timezone.localtime()}
