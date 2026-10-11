from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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
