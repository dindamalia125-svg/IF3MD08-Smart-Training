from unittest import mock

from django.test import TestCase
from django.urls import reverse

from accounts.models import AuditLog
from training.ai_parser import parse_manpower
from training.factories import add_capaian, make_admin, make_master, make_trainee, make_trainer
from training.models import Capaian, ProsesTrainee, Sertifikat, Trainee


class Base(TestCase):
    def setUp(self):
        make_admin()
        self.trainer = make_trainer()
        self.shifts, self.linis, self.proses = make_master()
        self.client.login(username="trainer_dedi", password="trainer12345")


class ParserTests(Base):
    def test_rule_based_parser(self):
        rows = parse_manpower("Andi Pratama - TR-0142 - A\nMaya Putri, TR-0098, b\n1. Rudi Hartono | TR-0177 | 3x2\nSiti ???", ["A", "B", "3x2"])
        self.assertEqual([(r["nama"], r["badge"], r["shift"]) for r in rows[:3]],
                         [("Andi Pratama", "TR-0142", "A"), ("Maya Putri", "TR-0098", "B"), ("Rudi Hartono", "TR-0177", "3x2")])
        self.assertEqual(rows[3]["badge"], "")


class ManpowerTests(Base):
    def test_empty_text(self):
        r = self.client.post(reverse("training:manpower"), {"action": "proses", "teks": "   "})
        self.assertContains(r, "Teks kosong")

    def test_parse_marks_failed_and_duplicate_rows(self):
        make_trainee("TR-0098", "Maya Lama", self.shifts["B"])
        teks = "Andi Pratama - TR-0142 - A\nMaya Putri - TR-0098 - B\nSiti ???"
        r = self.client.post(reverse("training:manpower"), {"action": "proses", "teks": teks})
        self.assertContains(r, "Nomor Badge sudah ada (duplikat), baris ditolak")
        self.assertContains(r, "AI gagal memisahkan baris")

    def test_save_only_valid_rows(self):
        make_trainee("TR-0098", "Maya Lama", self.shifts["B"])
        data = {"action": "simpan", "nama": ["Andi Pratama", "Maya Putri", "Rudi", "Dobel"],
                "badge": ["TR-0142", "TR-0098", "TR-0177", "TR-0142"], "shift": ["A", "B", "3x2", "A"]}
        r = self.client.post(reverse("training:manpower"), data)
        self.assertContains(r, "2 baris berhasil disimpan, 2 baris ditolak")
        self.assertEqual(Trainee.objects.count(), 3)
        self.assertEqual(Trainee.objects.get(badge="TR-0098").nama, "Maya Lama")
        self.assertTrue(AuditLog.objects.filter(aktivitas="Parsing manpower").exists())


def _docx_bytes(paragraphs=(), table=None):
    """Bangun dokumen Word kecil di memori untuk tes."""
    from io import BytesIO

    from docx import Document

    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    if table:
        t = doc.add_table(rows=0, cols=len(table[0]))
        for row in table:
            cells = t.add_row().cells
            for c, v in zip(cells, row):
                c.text = v
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


class DocxManpowerTests(Base):
    url_name = "training:manpower"

    def _upload(self, content, name="manpower.docx"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        f = SimpleUploadedFile(name, content)
        return self.client.post(reverse(self.url_name), {"action": "proses", "dokumen": f})

    def test_extract_paragraphs_and_table_skips_header(self):
        from io import BytesIO

        from training.docx_reader import extract_text

        data = _docx_bytes(["Daftar Karyawan Baru", "Andi Pratama - TR-0142 - A"],
                           table=[["No", "Nama", "Nomor Badge", "Shift"],
                                  ["1", "Maya Putri", "TR-0098", "B"]])
        text = extract_text(BytesIO(data))
        self.assertIn("Andi Pratama - TR-0142 - A", text)
        self.assertIn("1 | Maya Putri | TR-0098 | B", text)
        self.assertNotIn("Nomor Badge", text)

    def test_upload_docx_parses_rows(self):
        data = _docx_bytes(["Andi Pratama - TR-0142 - A"],
                           table=[["No", "Nama", "Nomor Badge", "Shift"], ["1", "Maya Putri", "TR-0098", "B"]])
        r = self._upload(data)
        self.assertContains(r, "Andi Pratama")
        self.assertContains(r, "Maya Putri")
        self.assertContains(r, "manpower.docx")
        self.assertEqual([x["status"] for x in r.context["rows"] if x["badge"] in ("TR-0142", "TR-0098")],
                         ["ok", "ok"])

    def test_wrong_extension_rejected(self):
        r = self._upload(b"hello", name="manpower.pdf")
        self.assertContains(r, "Format file tidak didukung")

    def test_corrupt_docx_rejected(self):
        r = self._upload(b"bukan zip", name="rusak.docx")
        self.assertContains(r, "File tidak dapat dibaca")

    def test_empty_docx_rejected(self):
        r = self._upload(_docx_bytes([]))
        self.assertContains(r, "Dokumen kosong")

    def test_upload_then_save(self):
        r = self._upload(_docx_bytes(["Andi Pratama - TR-0142 - A"]))
        row = next(x for x in r.context["rows"] if x["badge"] == "TR-0142")
        r = self.client.post(reverse(self.url_name), {"action": "simpan", "nama": [row["nama"]],
                                                      "badge": [row["badge"]], "shift": [row["shift"]]})
        self.assertTrue(Trainee.objects.filter(badge="TR-0142").exists())


class CapaianTests(Base):
    def setUp(self):
        super().setUp()
        self.t = make_trainee(shift=self.shifts["A"], lini=self.linis["Line 2"])
        self.url = reverse("training:capaian")
        self.data = {"trainee": self.t.pk, "proses": self.proses["PRC-001"].pk, "tanggal": "2026-10-10",
                     "output": 118, "reject": 2}

    def test_save_and_audit(self):
        r = self.client.post(self.url, self.data, follow=True)
        self.assertContains(r, "Capaian tersimpan, riwayat sebelumnya tidak dihapus")
        self.assertEqual(Capaian.objects.filter(aktif=True).count(), 1)
        self.assertTrue(ProsesTrainee.objects.filter(trainee=self.t).exists())
        self.assertTrue(AuditLog.objects.filter(aktivitas="Input data", keterangan__contains="output 118").exists())

    def test_negative_and_non_numeric_rejected(self):
        for bad in ({"output": -5}, {"output": "abc"}, {"reject": ""}):
            r = self.client.post(self.url, {**self.data, **bad})
            self.assertContains(r, "Isian wajib berupa angka dan tidak negatif")
        self.assertEqual(Capaian.objects.count(), 0)

    def test_overwrite_requires_confirmation_and_keeps_history(self):
        self.client.post(self.url, self.data)
        r = self.client.post(self.url, {**self.data, "output": 125})
        self.assertContains(r, "sudah ada. Timpa data?")
        self.assertEqual(Capaian.objects.count(), 1)
        self.client.post(self.url, {**self.data, "output": 125, "timpa": "1"})
        self.assertEqual(Capaian.objects.count(), 2)  # riwayat lama tidak dihapus
        self.assertEqual(Capaian.objects.get(aktif=True).output, 125)
        self.assertFalse(Capaian.objects.get(aktif=False).aktif)


class SearchTests(Base):
    def setUp(self):
        super().setUp()
        self.a = make_trainee("TR-0142", "Andi Pratama", self.shifts["A"], self.linis["Line 2"])
        make_trainee("TR-0188", "Andi Saputra", self.shifts["B"])

    def test_not_found(self):
        r = self.client.get(reverse("training:penelusuran"), {"q": "zzz"})
        self.assertContains(r, "Data trainee tidak ditemukan")

    def test_exact_badge_goes_to_profile(self):
        r = self.client.get(reverse("training:penelusuran"), {"q": "TR-0142"})
        self.assertEqual(r.status_code, 302)
        r = self.client.get(r["Location"])
        self.assertContains(r, "Riwayat Shift")
        self.assertContains(r, "Andi Pratama")

    def test_multiple_results_list(self):
        r = self.client.get(reverse("training:penelusuran"), {"q": "Andi"})
        self.assertContains(r, "2 trainee cocok")


class EvaluasiTests(Base):
    def setUp(self):
        super().setUp()
        self.t = make_trainee("TR-0142", "Andi Pratama", self.shifts["A"], self.linis["Line 2"])
        add_capaian(self.t, self.proses["PRC-001"], [114] * 5, self.trainer)   # 95% -> qualified
        add_capaian(self.t, self.proses["PRC-003"], [140] * 5, self.trainer)   # 70% -> belum
        self.url = reverse("training:evaluasi", args=[self.t.pk])
        self.pt_ok = ProsesTrainee.objects.get(trainee=self.t, proses=self.proses["PRC-001"])
        self.pt_no = ProsesTrainee.objects.get(trainee=self.t, proses=self.proses["PRC-003"])

    def test_ai_recommendation(self):
        r = self.client.get(self.url)
        self.assertContains(r, "✔ Qualified")
        self.assertContains(r, "✖ Belum qualified")
        self.assertContains(r, "Rekomendasi AI dievaluasi")

    def test_print_when_approved_creates_certificate_and_pdf(self):
        r = self.client.post(self.url, {"action": "cetak", f"verifikasi_{self.pt_ok.pk}": "setuju",
                                        f"verifikasi_{self.pt_no.pk}": "setuju"}, follow=True)
        self.assertContains(r, "Sertifikat berhasil dibuat")
        self.assertEqual(Sertifikat.objects.count(), 1)  # hanya proses qualified
        self.pt_ok.refresh_from_db()
        self.assertEqual(self.pt_ok.status, "QUALIFIED")
        self.assertTrue(AuditLog.objects.filter(aktivitas="Cetak sertifikat").exists())
        cert = Sertifikat.objects.get()
        self.assertTrue(cert.nomor.startswith("CERT-"))
        pdf = self.client.get(reverse("training:sertifikat_pdf"), {"ids": cert.pk})
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(b"".join(pdf.streaming_content).startswith(b"%PDF"))

    def test_not_approved_or_not_qualified_prints_nothing(self):
        r = self.client.post(self.url, {"action": "cetak", f"verifikasi_{self.pt_ok.pk}": "tidak",
                                        f"verifikasi_{self.pt_no.pk}": "setuju"})
        self.assertContains(r, "tombol Cetak Sertifikat dinonaktifkan")
        self.assertEqual(Sertifikat.objects.count(), 0)

    def test_pdf_failure_rolls_back(self):
        with mock.patch("training.views.build_certificates_pdf", side_effect=RuntimeError("boom")):
            r = self.client.post(self.url, {"action": "cetak", f"verifikasi_{self.pt_ok.pk}": "setuju"})
        self.assertContains(r, "Gagal membuat PDF sertifikat. Silakan coba lagi.")
        self.assertEqual(Sertifikat.objects.count(), 0)
        self.pt_ok.refresh_from_db()
        self.assertEqual(self.pt_ok.status, "TRAINING")
        # mencoba lagi berhasil
        r = self.client.post(self.url, {"action": "cetak", f"verifikasi_{self.pt_ok.pk}": "setuju"}, follow=True)
        self.assertContains(r, "Sertifikat berhasil dibuat")


class PenelusuranListTests(Base):
    def setUp(self):
        super().setUp()
        self.a = make_trainee("TR-0142", "Andi Pratama", self.shifts["A"], self.linis["Line 2"])
        self.b = make_trainee("TR-0098", "Maya Putri", self.shifts["B"])

    def test_empty_query_lists_all_trainees(self):
        r = self.client.get(reverse("training:penelusuran"))
        self.assertContains(r, "Seluruh karyawan (2)")
        self.assertContains(r, "Andi Pratama")
        self.assertContains(r, "Maya Putri")

    def test_change_shift_updates_history_and_audit(self):
        r = self.client.post(reverse("training:trainee_shift_update", args=[self.a.pk]),
                             {"shift": self.shifts["C"].pk, "next": reverse("training:penelusuran")}, follow=True)
        self.assertContains(r, "diubah dari A ke C")
        self.a.refresh_from_db()
        self.assertEqual(self.a.shift.kode, "C")
        self.assertEqual(self.a.riwayat_shift.filter(selesai__isnull=True).count(), 1)
        self.assertEqual(self.a.riwayat_shift.count(), 2)
        self.assertTrue(AuditLog.objects.filter(objek="Shift trainee", keterangan__contains="A → C").exists())

    def test_invalid_shift_rejected(self):
        r = self.client.post(reverse("training:trainee_shift_update", args=[self.a.pk]), {"shift": 9999}, follow=True)
        self.assertContains(r, "Pilih shift yang valid")
        self.a.refresh_from_db()
        self.assertEqual(self.a.shift.kode, "A")

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(reverse("training:trainee_shift_update", args=[self.a.pk])).status_code, 405)
