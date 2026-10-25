from io import BytesIO

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from accounts.models import AuditLog
from training.factories import add_capaian, make_master, make_trainee, make_trainer


class ExportTests(TestCase):
    def setUp(self):
        self.trainer = make_trainer()
        self.client.login(username="trainer_dedi", password="trainer12345")
        shifts, _, self.proses = make_master()
        t = make_trainee(shift=shifts["A"])
        add_capaian(t, self.proses["PRC-001"], [118], self.trainer)  # kemarin
        self.kemarin = (timezone.localdate() - timezone.timedelta(days=1)).isoformat()

    def test_no_data_shows_error(self):
        r = self.client.post(reverse("reports:ekspor"), {"jenis": "harian", "periode_harian": "2020-01-01", "format": "xlsx"})
        self.assertContains(r, "Periode belum dipilih / tidak ada data pada periode ini")

    def test_empty_period_shows_error(self):
        r = self.client.post(reverse("reports:ekspor"), {"jenis": "harian", "periode_harian": "", "format": "xlsx"})
        self.assertContains(r, "Periode belum dipilih")

    def test_xlsx_flow(self):
        data = {"jenis": "harian", "periode_harian": self.kemarin, "format": "xlsx"}
        r = self.client.post(reverse("reports:ekspor"), data, follow=True)
        self.assertContains(r, "Laporan siap diunduh")
        self.assertContains(r, f"rekap_training_{self.kemarin}.xlsx")
        f = self.client.get(reverse("reports:unduh"), {"jenis": "harian", "periode_harian": self.kemarin, "format": "xlsx"})
        ws = load_workbook(BytesIO(f.content)).active
        self.assertEqual([c.value for c in ws[3]], ["Emp No.", "Nama", "Proses", "Output", "Reject", "% Target"])
        self.assertEqual(ws["D4"].value, 118)
        self.assertAlmostEqual(ws["F4"].value, 118 / 120, places=2)
        self.assertTrue(AuditLog.objects.filter(aktivitas="Ekspor laporan").exists())

    def test_pdf_monthly(self):
        periode = self.kemarin[:7]
        f = self.client.get(reverse("reports:unduh"), {"jenis": "bulanan", "periode_bulanan": periode, "format": "pdf"})
        self.assertEqual(f["Content-Type"], "application/pdf")
        self.assertTrue(f.content.startswith(b"%PDF"))
