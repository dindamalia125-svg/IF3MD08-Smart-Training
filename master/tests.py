from django.test import TestCase
from django.urls import reverse

from accounts.models import AuditLog
from master.models import Lini, Proses, Shift
from training.factories import add_capaian, make_admin, make_master, make_trainee, make_trainer


class MasterTests(TestCase):
    def setUp(self):
        make_admin()
        self.client.login(username="admin", password="admin12345")

    def test_create_proses_and_audit(self):
        r = self.client.post(reverse("master:proses_add"), {"kode": "prc-010", "nama": "Welding",
                                                            "target_harian": 90, "durasi_maks_hari": 12}, follow=True)
        self.assertContains(r, "Data proses berhasil disimpan")
        self.assertTrue(Proses.objects.filter(kode="PRC-010").exists())
        self.assertTrue(AuditLog.objects.filter(objek="Master proses", aktivitas="Tambah data").exists())

    def test_duplicate_kode_and_non_numeric(self):
        Proses.objects.create(kode="PRC-001", nama="A", target_harian=1, durasi_maks_hari=1)
        r = self.client.post(reverse("master:proses_add"), {"kode": "PRC-001", "nama": "B", "target_harian": "x",
                                                            "durasi_maks_hari": ""})
        self.assertContains(r, "Kode proses sudah ada")
        self.assertContains(r, "harus berupa angka")
        self.assertEqual(Proses.objects.count(), 1)

    def test_edit_logs_diff(self):
        p = Proses.objects.create(kode="PRC-003", nama="Inspeksi", target_harian=180, durasi_maks_hari=10)
        self.client.post(reverse("master:proses_edit", args=[p.pk]),
                         {"kode": "PRC-003", "nama": "Inspeksi", "target_harian": 200, "durasi_maks_hari": 10})
        self.assertTrue(AuditLog.objects.filter(keterangan__contains="target harian 180 → 200").exists())

    def test_delete_blocked_when_used(self):
        _, _, proses = make_master()
        t = make_trainee()
        add_capaian(t, proses["PRC-001"], [100])
        r = self.client.post(reverse("master:proses_delete", args=[proses["PRC-001"].pk]), follow=True)
        self.assertContains(r, "tidak dapat dihapus")
        self.assertTrue(Proses.objects.filter(kode="PRC-001").exists())

    def test_shift_and_lini_crud(self):
        r = self.client.post(reverse("master:shift_lini"), {"form_type": "shift", "shift-kode": "D", "shift-nama": "Shift D"}, follow=True)
        self.assertContains(r, "Data berhasil disimpan")
        r = self.client.post(reverse("master:shift_lini"), {"form_type": "shift", "shift-kode": "D", "shift-nama": "Dobel"})
        self.assertContains(r, "Kode shift sudah ada")
        self.client.post(reverse("master:shift_lini"), {"form_type": "lini", "lini-nama": "Line 5", "lini-lokasi": "Gedung C"})
        self.assertTrue(Lini.objects.filter(nama="Line 5").exists())
        self.assertEqual(Shift.objects.filter(kode="D").count(), 1)

    def test_trainer_forbidden(self):
        self.client.logout()
        make_trainer()
        self.client.login(username="trainer_dedi", password="trainer12345")
        r = self.client.get(reverse("master:proses_list"))
        self.assertEqual(r.status_code, 302)
