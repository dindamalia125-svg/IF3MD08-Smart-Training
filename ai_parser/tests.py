import io
import json
from unittest import mock
from urllib.error import URLError

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from docx import Document

from accounts.models import AuditLog
from ai_parser import header_ai
from ai_parser.forms import DocumentUploadForm
from ai_parser.models import Manpower
from ai_parser.pdf_parser import parse_pdf
from ai_parser.word_parser import parse_docx, split_department, validate_record
from training.factories import make_admin, make_master, make_trainer

HEADERS = ["No.", "Emp. No", "Employee Name", "Gender", "Sect/Dept", "Shift", "Position",
           "Employment Status", "Replacement"]
ROWS = [
    ["1", "20366", "Rizky Insani", "Male", "1340 / Tech4", "Normal", "Engineer", "Contract", "Additional"],
    ["2", "98420", "Alya Dzihni", "Female", "2700 / Haemo", "Normal", "Operator", "Contract", "Additional"],
    ["3", "98421", "Andini", "Female", "2700 / Haemo", "Normal", "Operator", "Contract", "Additional"],
]


def make_docx(rows=ROWS, headers=HEADERS, join_text="The above staff shall join August 06th 2026"):
    doc = Document()
    doc.add_paragraph("Subject : New Recruitment")
    table = doc.add_table(rows=1, cols=len(headers))
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h
    for row in rows:
        cells = table.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = v
    if join_text:
        doc.add_paragraph(join_text)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


PDF_LINES = [
    "Please find list of new recruitment for as follows:",
    "No. Emp. No Employee Name Gender Sect/Dept Shift Position Employment Status Replacement",
    "1 20366 Rizky Insani Male 1340 / Tech4 Normal Engineer Contract Additional",
    "2 41411 Erwin Nandra Volta Male 1340 / Tech4 Normal Technician Contract 41251 / Moh Valikhajar",
    "3 98420 Alya Dzihni Female 2700 / Haemo Normal Operator Contract Additional",
    "4 98421 Andini Female 2700 / Haemo Normal Operator Contract Additional",
    "The above staff shall join August 06th 2026",
]


def make_pdf(lines):
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 800
    for line in lines:
        c.drawString(30, y, line)
        y -= 16
    c.save()
    buf.seek(0)
    return buf


def upload(data, name="rekrut.docx"):
    return SimpleUploadedFile(name, data.getvalue() if hasattr(data, "getvalue") else data)


class ParseDocxTests(SimpleTestCase):
    def test_filters_haemo_and_reads_doc_date(self):
        r = parse_docx(make_docx(), ai_mapper=None)
        self.assertEqual([x["employee_number"] for x in r["accepted"]], ["98420", "98421"])
        self.assertEqual(r["summary"]["other_departments"], 1)
        self.assertEqual(r["summary"]["total_detected"], 3)
        self.assertEqual(r["accepted"][0]["doc"], "2026-08-06")
        self.assertEqual(r["accepted"][0]["remarks"], "Additional")
        self.assertEqual(r["summary"]["header_source"], "aturan")

    def test_missing_doc_date_gives_warning(self):
        r = parse_docx(make_docx(join_text=""), ai_mapper=None)
        self.assertIsNone(r["summary"]["join_date"])
        self.assertTrue(r["warnings"])

    def test_header_below_title_row(self):
        doc = Document()
        t = doc.add_table(rows=2, cols=len(HEADERS))
        t.rows[0].cells[0].text = "Daftar karyawan baru"
        for i, h in enumerate(HEADERS):
            t.rows[1].cells[i].text = h
        cells = t.add_row().cells
        for i, v in enumerate(ROWS[1]):
            cells[i].text = v
        buf = io.BytesIO()
        doc.save(buf)
        r = parse_docx(buf, ai_mapper=None)
        self.assertEqual(len(r["accepted"]), 1)

    def test_empty_name_wrong_dept_format_and_duplicate_need_review(self):
        rows = [
            ["1", "98420", "", "F", "2700 / Haemo", "", "Op", "C", ""],
            ["2", "98421", "Budi", "M", "Haemo", "", "Op", "C", ""],
            ["3", "98422", "Citra", "F", "2700 / Haemo", "", "Op", "C", ""],
            ["4", "98422", "Citra Dua", "F", "2700 / Haemo", "", "Op", "C", ""],
            ["5", "98423", "Dewi", "F", "2700 / Tech4", "", "Op", "C", ""],
        ]
        r = parse_docx(make_docx(rows), ai_mapper=None)
        reasons = " | ".join(i["reason"] for i in r["needs_review"])
        self.assertEqual([x["employee_number"] for x in r["accepted"]], ["98422"])
        self.assertIn("Field wajib kosong: Emp Name", reasons)
        self.assertIn("Format Sect/Dept tidak dikenali", reasons)
        self.assertIn("Emp No duplikat dalam file", reasons)
        self.assertIn("nama section bukan Haemo", reasons)
        self.assertEqual(r["accepted"][0]["shift"], "Normal")  # shift kosong -> Normal

    def test_unknown_headers_without_ai_raise_clear_error(self):
        headers = ["No", "Kolom A", "Kolom B", "Kolom C"]
        with self.assertRaisesMessage(ValueError, "Tabel recruitment tidak ditemukan"):
            parse_docx(make_docx([["1", "a", "b", "c"]], headers), ai_mapper=None)

    def test_unknown_headers_mapped_by_ai(self):
        headers = ["No", "Nomor Pegawai", "Nama Lengkap", "Bagian"]
        rows = [["1", "98420", "Alya", "2700 / Haemo"], ["2", "20366", "Rizky", "1340 / Tech4"]]
        seen = {}

        def fake_ai(labels):
            seen["labels"] = labels
            return {1: "employee_number", 2: "employee_name", 3: "department"}

        r = parse_docx(make_docx(rows, headers), ai_mapper=fake_ai)
        self.assertEqual([x["employee_number"] for x in r["accepted"]], ["98420"])
        self.assertEqual(r["summary"]["header_source"], "AI")
        self.assertEqual(seen["labels"], headers)  # hanya header yang dikirim, bukan data karyawan
        self.assertNotIn("Alya", json.dumps(seen["labels"]))

    def test_ai_cannot_override_rules_or_reuse_fields(self):
        headers = ["No", "Emp. No", "Nama Lengkap", "Bagian"]
        rows = [["1", "98420", "Alya", "2700 / Haemo"]]
        # AI salah: mencoba menimpa "Emp. No" (indeks 1, sudah dikenali aturan) menjadi employee_name
        # dan memakai employee_number untuk kolom kedua. Hanya pemetaan benar (2 dan 3) yang boleh dipakai.
        bad = lambda labels: {1: "employee_name", 2: "employee_name", 3: "department", 0: "employee_number"}  # noqa: E731
        r = parse_docx(make_docx(rows, headers), ai_mapper=bad)
        self.assertEqual(r["accepted"][0]["employee_number"], "98420")
        self.assertEqual(r["accepted"][0]["employee_name"], "Alya")

    def test_ai_returning_nothing_keeps_error(self):
        headers = ["No", "Kolom A", "Kolom B", "Kolom C"]
        with self.assertRaises(ValueError):
            parse_docx(make_docx([["1", "a", "b", "c"]], headers), ai_mapper=lambda labels: {})


class SectionSeparationTests(SimpleTestCase):
    def test_docx_groups_employees_per_section(self):
        r = parse_docx(make_docx(), ai_mapper=None)
        by_label = {g["label"]: g for g in r["sections"]}
        self.assertEqual(by_label["2700 / Haemo"]["count"], 2)
        self.assertEqual(by_label["1340 / Tech4"]["count"], 1)
        self.assertTrue(by_label["2700 / Haemo"]["is_target"])
        self.assertFalse(by_label["1340 / Tech4"]["is_target"])
        self.assertEqual(r["sections"][0]["label"], "2700 / Haemo")  # Haemo selalu di urutan pertama
        self.assertEqual(r["rejected"][0]["employee_name"], "Rizky Insani")

    def test_unrecognised_department_has_own_group(self):
        rows = [["1", "98420", "Alya", "Female", "Haemo saja", "Normal", "Operator", "Contract", "-"]]
        r = parse_docx(make_docx(rows), ai_mapper=None)
        self.assertEqual([g["label"] for g in r["sections"]], ["Tidak dikenali"])
        self.assertEqual(len(r["needs_review"]), 1)


class ParsePdfTests(SimpleTestCase):
    def test_separates_haemo_from_other_sections(self):
        r = parse_pdf(make_pdf(PDF_LINES))
        self.assertEqual([x["employee_number"] for x in r["accepted"]], ["98420", "98421"])
        self.assertEqual([x["employee_number"] for x in r["rejected"]], ["20366", "41411"])
        self.assertEqual(r["summary"]["join_date"], "2026-08-06")
        first = r["accepted"][0]
        self.assertEqual((first["shift"], first["position"], first["status"], first["remarks"]),
                         ("Normal", "Operator", "Contract", "Additional"))
        self.assertEqual(r["rejected"][1]["department"], "1340 / Tech4")

    def test_row_wrapped_over_two_lines_is_joined(self):
        lines = ["3 98420 Alya Dzihni Fadhilah", "Siregar Female 2700 / Haemo Normal Operator Contract Additional"]
        r = parse_pdf(make_pdf(lines))
        self.assertEqual(r["accepted"][0]["employee_name"], "Alya Dzihni Fadhilah Siregar")

    def test_same_result_as_word(self):
        pdf, word = parse_pdf(make_pdf(PDF_LINES)), parse_docx(make_docx(), ai_mapper=None)
        pick = lambda rows: [(x["employee_number"], x["employee_name"], x["position"], x["status"]) for x in rows]  # noqa: E731
        self.assertEqual(pick(pdf["accepted"])[0][:2], ("98420", "Alya Dzihni"))
        self.assertEqual(pick(pdf["accepted"]), pick(word["accepted"]))

    def test_scanned_pdf_without_text_gives_clear_error(self):
        with self.assertRaisesMessage(ValueError, "hasil scan"):
            parse_pdf(make_pdf([]))

    def test_pdf_without_employee_rows(self):
        with self.assertRaisesMessage(ValueError, "Baris karyawan tidak ditemukan"):
            parse_pdf(make_pdf(["Surat biasa tanpa tabel karyawan"]))

    def test_corrupt_pdf(self):
        with self.assertRaisesMessage(ValueError, "rusak"):
            parse_pdf(io.BytesIO(b"%PDF-1.4 ini bukan pdf yang benar"))


class SplitDepartmentTests(SimpleTestCase):
    def test_format_variants(self):
        for value in ["2700 / Haemo", "2700/Haemo", "2700 - Haemo", "2700-Haemo", "2700 : Haemo",
                      "2700 Haemo", "Haemo / 2700"]:
            self.assertEqual(split_department(value), ("2700", "Haemo"), value)

    def test_unrecognised_format(self):
        for value in ["", "Haemo", "2700"]:
            self.assertEqual(split_department(value)[0], "", value)

    def test_variant_for_other_department_is_not_haemo(self):
        code, _ = split_department("Tech4 - 1340")
        self.assertEqual(code, "1340")

    def test_dash_variant_is_accepted_end_to_end(self):
        rows = [["1", "98420", "Alya", "Female", "2700 - Haemo", "Normal", "Operator", "Contract", "Additional"]]
        r = parse_docx(make_docx(rows), ai_mapper=None)
        self.assertEqual(len(r["accepted"]), 1)
        self.assertEqual(r["needs_review"], [])


class ValidateRecordTests(SimpleTestCase):
    base = {"employee_number": "98420", "employee_name": "Alya", "department_code": "2700",
            "department_name": "Haemo", "doc": "2026-08-06"}

    def test_valid(self):
        rec, reasons = validate_record(dict(self.base))
        self.assertEqual(reasons, [])
        self.assertEqual(rec["shift"], "Normal")

    def test_float_emp_no_normalized(self):
        rec, _ = validate_record({**self.base, "employee_number": "98420.0"})
        self.assertEqual(rec["employee_number"], "98420")

    def test_invalid_cases(self):
        for change, text in [
            ({"employee_number": "9 8"}, "Format Emp No tidak valid"),
            ({"employee_name": "12345"}, "Emp Name tidak valid"),
            ({"doc": "06/08/2026"}, "Format DOC"),
            ({"department_code": "1340", "department_name": "Tech4"}, "Bukan section"),
            ({"position": "x" * 121}, "terlalu panjang"),
        ]:
            _, reasons = validate_record({**self.base, **change})
            self.assertTrue(any(text in x for x in reasons), (change, reasons))


class HeaderAiTests(SimpleTestCase):
    @override_settings(ANTHROPIC_API_KEY="")
    def test_no_key_returns_empty(self):
        with mock.patch.object(header_ai, "_call_claude") as call:
            self.assertEqual(header_ai.map_headers_with_ai(["a"]), {})
            call.assert_not_called()

    @override_settings(ANTHROPIC_API_KEY="test-key")
    def test_valid_response_filtered(self):
        raw = '```json\n{"1": "employee_number", "2": "bukan_field", "9": "employee_name", "x": "shift"}\n```'
        with mock.patch.object(header_ai, "_call_claude", return_value=header_ai.re.sub(r"^```(?:json)?|```$", "", raw, flags=header_ai.re.M).strip()):
            self.assertEqual(header_ai.map_headers_with_ai(["No", "Nomor", "Nama"]), {1: "employee_number"})

    @override_settings(ANTHROPIC_API_KEY="test-key")
    def test_failures_return_empty(self):
        for exc in (URLError("offline"), TimeoutError(), ValueError("x")):
            with mock.patch.object(header_ai, "_call_claude", side_effect=exc):
                self.assertEqual(header_ai.map_headers_with_ai(["a"]), {})
        with mock.patch.object(header_ai, "_call_claude", return_value="[1,2]"):
            self.assertEqual(header_ai.map_headers_with_ai(["a"]), {})
        with mock.patch.object(header_ai, "_call_claude", return_value="bukan json"):
            self.assertEqual(header_ai.map_headers_with_ai(["a"]), {})


class UploadFormTests(SimpleTestCase):
    def check(self, f):
        form = DocumentUploadForm({}, {"document": f})
        return form.is_valid(), form.errors.get("document", [""])[0]

    def test_rules(self):
        ok, _ = self.check(upload(make_docx()))
        self.assertTrue(ok)
        self.assertIn("Word (.docx) atau PDF", self.check(upload(make_docx(), "a.txt"))[1])
        self.assertIn("bukan PDF", self.check(upload(make_docx(), "a.pdf"))[1])  # isi tidak sesuai ekstensi
        ok_pdf, _ = self.check(upload(make_pdf(PDF_LINES), "a.pdf"))
        self.assertTrue(ok_pdf)
        self.assertIn("File kosong", self.check(SimpleUploadedFile("a.docx", b""))[1])
        self.assertIn("rusak", self.check(SimpleUploadedFile("a.docx", b"bukan zip"))[1])
        big = SimpleUploadedFile("a.docx", b"PK\x03\x04" + b"0" * (10 * 1024 * 1024))
        self.assertIn("maksimal 10 MB", self.check(big)[1])


class ViewTests(TestCase):
    def setUp(self):
        make_admin()
        make_trainer()
        make_master()
        self.login_trainer()

    def login_trainer(self):
        self.client.logout()
        self.client.login(username="trainer_dedi", password="trainer12345")

    def login_admin(self):
        self.client.logout()
        self.client.login(username="admin", password="admin12345")

    def do_upload(self, data=None, name="rekrut.docx"):
        return self.client.post(reverse("ai_parser:upload_document"),
                                {"document": upload(data or make_docx(), name)})

    def confirm_data(self, preview_response, **overrides):
        """Susun POST konfirmasi dari isi form preview (nilai default sebagaimana ditampilkan)."""
        rows = [i for i in preview_response.context["rows"]]
        data = {"count": str(len(rows))}
        for i, item in enumerate(rows):
            r = item["record"]
            data.update({
                f"employee_number-{i}": r["employee_number"], f"employee_name-{i}": r["employee_name"],
                f"doc-{i}": r["doc"] or "", f"position-{i}": r["position"],
                f"department-{i}": f"{r['department_code']} / {r['department_name']}" if r["department_code"] else r["department_name"],
                f"shift-{i}": r["shift"], f"status-{i}": r["status"], f"remarks-{i}": r["remarks"],
            })
            if item["checked"]:
                data[f"pilih-{i}"] = "1"
        data.update(overrides)
        return data

    # ---- akses
    def test_access_control(self):
        self.client.logout()
        for name in ("manpower_list", "upload_document", "preview_import"):
            r = self.client.get(reverse(f"ai_parser:{name}"))
            self.assertEqual(r.status_code, 302)
            self.assertIn("/masuk", r["Location"]) if "/masuk" in r["Location"] else self.assertIn("login", r["Location"].lower())
        self.login_trainer()
        self.assertEqual(self.client.get(reverse("ai_parser:manpower_list")).status_code, 200)
        self.login_admin()
        self.assertEqual(self.client.get(reverse("ai_parser:manpower_list")).status_code, 200)

    def test_nav_has_manpower_data_for_both_roles(self):
        for login in (self.login_trainer, self.login_admin):
            login()
            self.assertContains(self.client.get(reverse("ai_parser:manpower_list")), "Manpower Data")
            labels = [n["label"] for n in self.client.get(reverse("ai_parser:manpower_list")).context["nav_items"]]
            self.assertIn("Manpower Data", labels)

    # ---- alur upload -> preview -> konfirmasi
    def test_full_flow_saves_only_after_confirmation(self):
        r = self.do_upload()
        self.assertRedirects(r, reverse("ai_parser:preview_import"))
        self.assertEqual(Manpower.objects.count(), 0)  # belum disimpan
        preview = self.client.get(reverse("ai_parser:preview_import"))
        self.assertContains(preview, "98420")
        self.assertEqual(len(preview.context["rows"]), 2)
        self.assertEqual(Manpower.objects.count(), 0)
        r = self.client.post(reverse("ai_parser:confirm_import"), self.confirm_data(preview))
        self.assertRedirects(r, reverse("ai_parser:manpower_list"))
        self.assertEqual(Manpower.objects.count(), 2)
        m = Manpower.objects.get(employee_number="98420")
        self.assertEqual((m.section_code, m.section, str(m.doc), m.remarks), ("2700", "Haemo", "2026-08-06", "Additional"))
        log = AuditLog.objects.get(aktivitas="Parsing manpower")
        self.assertIn("2 disimpan", log.keterangan)
        # sesi preview dibersihkan
        self.assertRedirects(self.client.get(reverse("ai_parser:preview_import")), reverse("ai_parser:upload_document"))

    def test_confirm_creates_trainee_and_shift_change_syncs(self):
        from master.models import Shift
        from training.models import Trainee

        preview = self.client.get(self.do_upload()["Location"])
        self.client.post(reverse("ai_parser:confirm_import"), self.confirm_data(preview))
        trainee = Trainee.objects.get(emp_no="98420")
        self.assertEqual(trainee.nama, "Alya Dzihni")
        self.assertEqual(str(trainee.mulai_training), "2026-08-06")
        # Emp No yang sudah menjadi Trainee ditandai duplikat saat upload ulang
        again = self.client.get(self.do_upload()["Location"])
        self.assertTrue(all(i["already_exists"] for i in again.context["rows"]))
        # ubah shift di Manpower -> shift Trainee ikut berubah bila ada di master Shift
        shift = Shift.objects.first()
        m = Manpower.objects.get(employee_number="98420")
        self.client.post(reverse("ai_parser:update_assignment", args=[m.pk]),
                         json.dumps({"field": "shift", "value": shift.kode}), content_type="application/json")
        trainee.refresh_from_db()
        self.assertEqual(trainee.shift_id, shift.pk)

    def test_pdf_upload_full_flow_with_sections(self):
        r = self.do_upload(make_pdf(PDF_LINES), "rekrut.pdf")
        self.assertRedirects(r, reverse("ai_parser:preview_import"))
        self.assertEqual(Manpower.objects.count(), 0)
        preview = self.client.get(reverse("ai_parser:preview_import"))
        self.assertContains(preview, "Pemisahan karyawan per section")
        self.assertContains(preview, "1340 / Tech4")
        self.assertContains(preview, "Rizky Insani")  # section lain terlihat, tetapi tidak diimpor
        self.client.post(reverse("ai_parser:confirm_import"), self.confirm_data(preview))
        self.assertEqual(sorted(Manpower.objects.values_list("employee_number", flat=True)), ["98420", "98421"])

    def test_scanned_pdf_upload_shows_clear_error(self):
        r = self.do_upload(make_pdf([]), "scan.pdf")
        self.assertContains(r, "hasil scan")
        self.assertEqual(Manpower.objects.count(), 0)

    def test_dropzone_on_input_manpower_ai_page_and_upload_page(self):
        for name in ("training:manpower", "ai_parser:upload_document"):
            page = self.client.get(reverse(name))
            self.assertContains(page, 'id="dz"')
            self.assertContains(page, reverse("ai_parser:upload_document"))
            self.assertContains(page, "dropzone.js")

    def test_user_can_fix_review_row_in_preview(self):
        rows = [["1", "98420", "", "F", "2700 / Haemo", "", "Op", "C", ""]]
        self.do_upload(make_docx(rows))
        preview = self.client.get(reverse("ai_parser:preview_import"))
        data = self.confirm_data(preview, **{"employee_name-0": "Alya Diperbaiki", "pilih-0": "1"})
        self.client.post(reverse("ai_parser:confirm_import"), data)
        self.assertEqual(Manpower.objects.get().employee_name, "Alya Diperbaiki")

    def test_unfixed_invalid_row_is_rejected_on_confirm(self):
        rows = [["1", "98420", "", "F", "2700 / Haemo", "", "Op", "C", ""]]
        self.do_upload(make_docx(rows))
        preview = self.client.get(reverse("ai_parser:preview_import"))
        self.client.post(reverse("ai_parser:confirm_import"), self.confirm_data(preview, **{"pilih-0": "1"}))
        self.assertEqual(Manpower.objects.count(), 0)
        self.assertIn("1 tidak valid", AuditLog.objects.get(aktivitas="Parsing manpower").keterangan)

    def test_tampered_other_department_is_rejected(self):
        self.do_upload()
        preview = self.client.get(reverse("ai_parser:preview_import"))
        data = self.confirm_data(preview, **{"department-0": "1340 / Tech4"})
        self.client.post(reverse("ai_parser:confirm_import"), data)
        self.assertEqual(list(Manpower.objects.values_list("employee_number", flat=True)), ["98421"])

    def test_duplicates_in_db_skipped_and_marked(self):
        Manpower.objects.create(employee_number="98420", employee_name="Sudah Ada")
        self.do_upload()
        preview = self.client.get(reverse("ai_parser:preview_import"))
        self.assertContains(preview, "sudah ada di database")
        self.client.post(reverse("ai_parser:confirm_import"), self.confirm_data(preview, **{"pilih-0": "1"}))
        self.assertEqual(Manpower.objects.get(employee_number="98420").employee_name, "Sudah Ada")
        self.assertEqual(Manpower.objects.count(), 2)

    def test_duplicate_emp_no_inside_confirm_post(self):
        self.do_upload()
        preview = self.client.get(reverse("ai_parser:preview_import"))
        data = self.confirm_data(preview, **{"employee_number-1": "98420", "pilih-1": "1"})
        self.client.post(reverse("ai_parser:confirm_import"), data)
        self.assertEqual(Manpower.objects.count(), 1)

    def test_confirm_without_preview_and_get(self):
        r = self.client.post(reverse("ai_parser:confirm_import"), {"count": "1"})
        self.assertRedirects(r, reverse("ai_parser:upload_document"))
        self.assertEqual(self.client.get(reverse("ai_parser:confirm_import")).status_code, 405)

    # ---- error upload
    def test_upload_errors_are_clear(self):
        r = self.do_upload(b"PK\x03\x04 bukan docx sebenarnya")
        self.assertContains(r, "File rusak atau bukan dokumen Word")
        r = self.do_upload(make_docx([["1", "a", "b", "c"]], ["No", "Kolom A", "Kolom B", "Kolom C"]))
        self.assertContains(r, "Tabel recruitment tidak ditemukan")
        r = self.do_upload(make_docx(), "rekrut.txt")
        self.assertContains(r, "Word (.docx) atau PDF")
        self.assertEqual(Manpower.objects.count(), 0)

    def test_unexpected_error_hides_internal_details(self):
        with mock.patch("ai_parser.views.parse_docx", side_effect=RuntimeError("rahasia internal")):
            r = self.do_upload()
        self.assertContains(r, "Dokumen gagal diproses")
        self.assertNotContains(r, "rahasia internal")

    def test_upload_with_ai_header_mapping(self):
        headers = ["No", "Nomor Pegawai", "Nama Lengkap", "Bagian"]
        rows = [["1", "98420", "Alya", "2700 / Haemo"]]
        with mock.patch("ai_parser.word_parser.map_headers_with_ai",
                        return_value={1: "employee_number", 2: "employee_name", 3: "department"}):
            r = self.do_upload(make_docx(rows, headers))
        self.assertRedirects(r, reverse("ai_parser:preview_import"))
        preview = self.client.get(reverse("ai_parser:preview_import"))
        self.assertContains(preview, "dengan bantuan AI")

    # ---- edit supervisor & shift
    def post_assignment(self, pk, field, value):
        return self.client.post(reverse("ai_parser:update_assignment", args=[pk]),
                                json.dumps({"field": field, "value": value}), content_type="application/json")

    def test_update_supervisor_and_shift_with_audit(self):
        m = Manpower.objects.create(employee_number="98420", employee_name="Alya")
        self.assertTrue(self.post_assignment(m.pk, "supervisor", "Pak Budi").json()["ok"])
        self.assertTrue(self.post_assignment(m.pk, "shift", "A").json()["ok"])
        m.refresh_from_db()
        self.assertEqual((m.supervisor, m.shift), ("Pak Budi", "A"))
        self.assertEqual(AuditLog.objects.filter(aktivitas="Ubah data").count(), 2)
        self.assertContains(self.client.get(reverse("ai_parser:manpower_list")), 'value="Pak Budi"')

    def test_update_rejects_bad_input(self):
        m = Manpower.objects.create(employee_number="98420", employee_name="Alya")
        self.assertEqual(self.post_assignment(m.pk, "shift", "Z9").status_code, 400)
        self.assertEqual(self.post_assignment(m.pk, "employee_name", "X").status_code, 400)
        self.assertEqual(self.post_assignment(m.pk, "supervisor", "x" * 121).status_code, 400)
        self.assertEqual(self.client.post(reverse("ai_parser:update_assignment", args=[m.pk]), "bukan json",
                                          content_type="application/json").status_code, 400)
        self.assertEqual(self.post_assignment(9999, "shift", "A").status_code, 404)

    def test_update_requires_login(self):
        m = Manpower.objects.create(employee_number="98420", employee_name="Alya")
        self.client.logout()
        r = self.post_assignment(m.pk, "shift", "A")
        self.assertEqual(r.status_code, 302)
        m.refresh_from_db()
        self.assertEqual(m.shift, "Normal")


class AutoReadDocxTests(SimpleTestCase):
    """Dokumen Word nyata (tabel bersarang, baris judul, teks tab) harus terbaca otomatis."""

    def _save(self, doc):
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf

    def _fill(self, container, title_rows=0):
        table = container.add_table(rows=0, cols=len(HEADERS))
        for _ in range(title_rows):
            cells = table.add_row().cells
            cells[0].text = "NEW RECRUITMENT"
            cells[0].merge(cells[-1])
        for values in [HEADERS] + ROWS:
            cells = table.add_row().cells
            for cell, value in zip(cells, values):
                cell.text = value
        return table

    def test_header_below_many_title_rows(self):
        doc = Document()
        self._fill(doc, title_rows=5)
        with mock.patch.object(header_ai, "_call_claude") as call:
            r = parse_docx(self._save(doc), ai_mapper=None)
            call.assert_not_called()
        self.assertEqual(r["summary"]["haemo_candidates"], 2)

    def test_nested_table(self):
        doc = Document()
        outer = doc.add_table(rows=1, cols=1)
        self._fill(outer.rows[0].cells[0])
        r = parse_docx(self._save(doc), ai_mapper=None)
        self.assertEqual(r["summary"]["total_detected"], 3)
        self.assertEqual(r["summary"]["haemo_candidates"], 2)

    def test_tab_separated_text(self):
        doc = Document()
        for values in [HEADERS] + ROWS:
            doc.add_paragraph("\t".join(values))
        r = parse_docx(self._save(doc), ai_mapper=None)
        self.assertEqual(r["summary"]["haemo_candidates"], 2)

    def test_ai_reads_document_without_table(self):
        doc = Document()
        doc.add_paragraph("Please add Alya Dzihni (98420) to Haemo 2700 and Andini (98421).")
        fake = mock.Mock(return_value=[
            {"employee_number": "98420", "employee_name": "Alya Dzihni", "department": "2700 / Haemo", "source_row": 1},
            {"employee_number": "98421", "employee_name": "Andini", "department": "2700 / Haemo", "source_row": 2},
            {"employee_number": "1", "employee_name": "Lain", "department": "1340 / Tech4", "source_row": 3},
        ])
        r = parse_docx(self._save(doc), ai_mapper=None, ai_extractor=fake)
        fake.assert_called_once()
        self.assertIn("98420", fake.call_args[0][0])  # teks dokumen sampai ke AI
        self.assertEqual(r["summary"]["header_source"], "AI")
        self.assertEqual(r["summary"]["haemo_candidates"], 2)
        self.assertEqual(r["summary"]["other_departments"], 1)
        self.assertTrue(any("dibaca otomatis oleh AI" in w for w in r["warnings"]))

    def test_ai_output_still_validated(self):
        doc = Document()
        doc.add_paragraph("daftar karyawan baru")
        bad = lambda text: [{"employee_number": "", "employee_name": "Tanpa Nomor", "department": "2700 / Haemo"}]
        r = parse_docx(self._save(doc), ai_mapper=None, ai_extractor=bad)
        self.assertEqual(r["summary"]["haemo_candidates"], 0)
        self.assertEqual(r["summary"]["needs_review"], 1)

    def test_no_table_and_ai_empty_raises(self):
        doc = Document()
        doc.add_paragraph("tidak ada tabel")
        with self.assertRaisesMessage(ValueError, "Tabel recruitment tidak ditemukan"):
            parse_docx(self._save(doc), ai_mapper=None, ai_extractor=lambda t: [])

    @override_settings(ANTHROPIC_API_KEY="")
    def test_extract_rows_no_key(self):
        with mock.patch.object(header_ai, "_call_claude_extract") as call:
            self.assertEqual(header_ai.extract_rows_with_ai("x"), [])
            call.assert_not_called()

    @override_settings(ANTHROPIC_API_KEY="k")
    def test_extract_rows_parses_and_survives_errors(self):
        raw = json.dumps([{"employee_number": 98420, "employee_name": "Alya", "department": "2700 / Haemo"}, "x"])
        with mock.patch.object(header_ai, "_call_claude_extract", return_value=raw):
            rows = header_ai.extract_rows_with_ai("teks")
        self.assertEqual(rows, [{"employee_number": "98420", "employee_name": "Alya", "gender": "",
                                 "department": "2700 / Haemo", "shift": "", "position": "", "status": "",
                                 "remarks": "", "doc": "", "source_row": 1}])
        for bad in (URLError("x"), TimeoutError()):
            with mock.patch.object(header_ai, "_call_claude_extract", side_effect=bad):
                self.assertEqual(header_ai.extract_rows_with_ai("teks"), [])
        with mock.patch.object(header_ai, "_call_claude_extract", return_value="bukan json"):
            self.assertEqual(header_ai.extract_rows_with_ai("teks"), [])


class JoinDateTests(SimpleTestCase):
    def test_phrasing_variants(self):
        from ai_parser.word_parser import extract_join_date_from_text as f
        for text, expected in [
            ("shall join on November 2, 2026", "2026-11-02"),
            ("will join on 6 August 2026", "2026-08-06"),
            ("Date of commencement: 06/08/2026", "2026-08-06"),
            ("Tanggal masuk: 6 Agustus 2026", "2026-08-06"),
            ("Joining date : 06-Aug-2026", "2026-08-06"),
            ("will be joining us on Monday, 3rd Aug 2026", "2026-08-03"),
            ("Sent: 1 Nov 2026. Hello", None),
        ]:
            self.assertEqual(f(text), expected, text)

    def test_date_inside_table_and_doc_column(self):
        headers = ["Emp. No", "Employee Name", "Sect/Dept", "DOC"]
        doc = Document()
        t = doc.add_table(rows=1, cols=4)
        for c, h in zip(t.rows[0].cells, headers):
            c.text = h
        for vals in [("98420", "Alya", "2700 / Haemo", "06/08/2026"), ("98421", "Andini", "2700 / Haemo", "")]:
            for c, v in zip(t.add_row().cells, vals):
                c.text = v
        doc.add_paragraph("The above staff shall join on 10 August 2026")
        buf = io.BytesIO(); doc.save(buf); buf.seek(0)
        r = parse_docx(buf, ai_mapper=None)
        self.assertEqual([x["doc"] for x in r["accepted"]], ["2026-08-06", "2026-08-10"])  # kolom DOC > tanggal umum

    def test_ai_finds_date_when_rules_fail(self):
        buf = make_docx(join_text="Mohon diproses segera.")
        r = parse_docx(buf, ai_mapper=lambda labels: {}, ai_extractor=None, ai_date=lambda text: "2026-08-06")
        self.assertEqual(r["summary"]["join_date"], "2026-08-06")
        self.assertTrue(any("DOC dibaca oleh AI" in w for w in r["warnings"]))

    @override_settings(ANTHROPIC_API_KEY="")
    def test_ai_date_no_key(self):
        self.assertIsNone(header_ai.find_join_date_with_ai("teks"))


class NewRecruitmentSubjectTests(SimpleTestCase):
    """Format HR nyata: tanggal DOC ada pada Subject / kalimat 'shall join' di atas tabel."""

    def _letter(self, *lines):
        doc = Document()
        for line in lines:
            doc.add_paragraph(line)
        table = doc.add_table(rows=1, cols=len(HEADERS))
        for i, h in enumerate(HEADERS):
            table.rows[0].cells[i].text = h
        for row in ROWS:
            cells = table.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = v
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf

    def test_doc_from_subject_only(self):
        buf = self._letter("September 03rd 2026", "Ref.\t:   02 / Job September / 2026",
                           "Subject\t:   New Recruitment on September 03rd 2026",
                           "Please find list of new recruitment for as follows:")
        r = parse_docx(buf, ai_mapper=None)
        self.assertEqual(r["summary"]["join_date"], "2026-09-03")
        self.assertTrue(all(x["doc"] == "2026-09-03" for x in r["accepted"]))

    def test_shall_join_with_company_name(self):
        buf = self._letter("Subject : New Recruitment", "The above staff shall join PT. JMS Batam on September 03rd 2026")
        self.assertEqual(parse_docx(buf, ai_mapper=None)["summary"]["join_date"], "2026-09-03")

    def test_join_phrase_beats_subject(self):
        buf = self._letter("Subject : New Recruitment on September 01st 2026", "The above staff shall join on September 03rd 2026")
        self.assertEqual(parse_docx(buf, ai_mapper=None)["summary"]["join_date"], "2026-09-03")
