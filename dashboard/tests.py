from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dashboard.views import add_months
from training.factories import add_capaian, make_admin, make_master, make_trainee, make_trainer
from training.models import ProsesTrainee


class SuperAdminDashboardTests(TestCase):
    def setUp(self):
        make_admin()
        self.client.login(username="admin", password="admin12345")

    def test_empty_dashboard(self):
        r = self.client.get(reverse("dashboard:super_admin"))
        self.assertContains(r, "Belum ada data pelatihan")

    def test_dashboard_with_data(self):
        shifts, linis, proses = make_master()
        t = make_trainee(shift=shifts["A"])
        add_capaian(t, proses["PRC-001"], [100, 110, 120])
        r = self.client.get(reverse("dashboard:super_admin"))
        self.assertContains(r, "Total Trainee")
        self.assertContains(r, "chartHarian")
        self.assertEqual(r.context["kpi"]["total"], 1)

    def test_trainer_cannot_open(self):
        make_trainer()
        self.client.logout()
        self.client.login(username="trainer_dedi", password="trainer12345")
        self.assertEqual(self.client.get(reverse("dashboard:super_admin")).status_code, 302)


class TrainerDashboardTests(TestCase):
    def setUp(self):
        make_trainer()
        self.client.login(username="trainer_dedi", password="trainer12345")
        self.shifts, self.linis, self.proses = make_master()

    def test_empty_shows_no_notifications(self):
        r = self.client.get(reverse("dashboard:trainer"))
        self.assertContains(r, "Tidak ada peringatan")
        self.assertContains(r, "Tidak ada notifikasi")
        self.assertEqual(r.context["bell"], 0)

    def test_training_warning_near_limit_only(self):
        today = timezone.localdate()
        near = make_trainee("TR-1", "Dekat", self.shifts["A"])
        far = make_trainee("TR-2", "Jauh", self.shifts["A"])
        ProsesTrainee.objects.create(trainee=near, proses=self.proses["PRC-001"], mulai=today - timedelta(days=13))  # 13/14
        ProsesTrainee.objects.create(trainee=far, proses=self.proses["PRC-001"], mulai=today - timedelta(days=3))
        r = self.client.get(reverse("dashboard:trainer"))
        self.assertContains(r, "Dekat")
        self.assertNotContains(r, "Jauh")
        self.assertContains(r, "93% · hampir batas")

    def test_contract_notification_30_days(self):
        today = timezone.localdate()
        make_trainee("EM-1", "Segera Habis", self.shifts["A"], self.linis["Line 2"], kontrak_berakhir=today + timedelta(days=10))
        make_trainee("EM-2", "Masih Lama", self.shifts["A"], kontrak_berakhir=today + timedelta(days=90))
        r = self.client.get(reverse("dashboard:trainer"))
        self.assertContains(r, "Segera Habis")
        self.assertNotContains(r, "Masih Lama")
        self.assertContains(r, "Line 2 · Gedung A Lt.2")


class FinishKontrakTests(TestCase):
    def setUp(self):
        make_trainer()
        make_admin()
        self.client.login(username="trainer_dedi", password="trainer12345")
        self.shifts, self.linis, self.proses = make_master()
        self.today = timezone.localdate()

    def make(self, emp, nama, days, **kw):
        return make_trainee(emp, nama, self.shifts["A"], kontrak_berakhir=self.today + timedelta(days=days), **kw)

    def test_default_is_12_months_grouped_by_month(self):
        self.make("K-1", "Bulan Depan", 20)
        self.make("K-2", "Sebelas Bulan", 330)
        self.make("K-3", "Tiga Belas Bulan", 400)  # di luar 12 bulan
        r = self.client.get(reverse("dashboard:finish_kontrak"))
        self.assertEqual(r.context["months"], 12)
        self.assertContains(r, "Bulan Depan")
        self.assertContains(r, "Sebelas Bulan")
        self.assertNotContains(r, "Tiga Belas Bulan")
        self.assertEqual(r.context["total"], 2)
        self.assertGreaterEqual(len(r.context["groups"]), 2)

    def test_filter_3_and_6_months(self):
        self.make("K-1", "Dekat", 30)
        self.make("K-2", "Lima Bulan", 150)
        self.make("K-3", "Sepuluh Bulan", 300)
        r3 = self.client.get(reverse("dashboard:finish_kontrak"), {"bulan": 3})
        r6 = self.client.get(reverse("dashboard:finish_kontrak"), {"bulan": 6})
        self.assertEqual(r3.context["total"], 1)
        self.assertEqual(r6.context["total"], 2)

    def test_invalid_month_param_falls_back_to_12(self):
        for bad in ("abc", "99", "-1", ""):
            r = self.client.get(reverse("dashboard:finish_kontrak"), {"bulan": bad})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.context["months"], 12, bad)

    def test_inactive_and_no_date_excluded_expired_listed_separately(self):
        self.make("K-1", "Sudah Lewat", -5)
        t = self.make("K-2", "Nonaktif", 40)
        t.aktif = False
        t.save()
        make_trainee("K-3", "Tanpa Tanggal", self.shifts["A"])
        r = self.client.get(reverse("dashboard:finish_kontrak"))
        self.assertEqual([c["t"].nama for c in r.context["expired"]], ["Sudah Lewat"])
        self.assertEqual(r.context["total"], 0)
        self.assertNotContains(r, "Nonaktif")
        self.assertEqual(r.context["tanpa_kontrak"], 1)

    def test_today_and_boundary_date_included(self):
        self.make("K-1", "Hari Ini", 0)
        make_trainee("K-2", "Batas", self.shifts["A"], kontrak_berakhir=add_months(self.today, 12))
        r = self.client.get(reverse("dashboard:finish_kontrak"))
        self.assertEqual(r.context["total"], 2)

    def test_empty_state(self):
        self.assertContains(self.client.get(reverse("dashboard:finish_kontrak")), "Tidak ada kontrak yang berakhir")

    def test_super_admin_can_view_but_not_open_profile_link(self):
        self.make("K-1", "Lihat Saja", 20)
        self.client.logout()
        self.client.login(username="admin", password="admin12345")
        r = self.client.get(reverse("dashboard:finish_kontrak"))
        self.assertContains(r, "Lihat Saja")
        self.assertNotContains(r, "Lihat profil")

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard:finish_kontrak")).status_code, 302)

    def test_add_months_clamps_day(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(add_months(date(2026, 10, 31), 12), date(2027, 10, 31))
        self.assertEqual(add_months(date(2028, 2, 29), 12), date(2029, 2, 28))
        self.assertEqual(add_months(date(2026, 11, 15), 3), date(2027, 2, 15))
