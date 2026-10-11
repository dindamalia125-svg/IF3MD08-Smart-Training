from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.audit import log
from accounts.models import AuditLog, User
from training.factories import make_admin, make_trainer


class LoginTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.trainer = make_trainer()

    def test_login_super_admin_goes_to_admin_dashboard(self):
        r = self.client.post(reverse("accounts:login"), {"identifier": "admin", "password": "admin12345"})
        self.assertRedirects(r, reverse("dashboard:super_admin"))

    def test_login_by_email_trainer_goes_to_trainer_dashboard(self):
        r = self.client.post(reverse("accounts:login"), {"identifier": "trainer_dedi@x.com", "password": "trainer12345"})
        self.assertRedirects(r, reverse("dashboard:trainer"))

    def test_wrong_password_shows_message(self):
        r = self.client.post(reverse("accounts:login"), {"identifier": "admin", "password": "salah"})
        self.assertContains(r, "Username atau Password Salah")

    def test_inactive_trainer_rejected_with_same_message(self):
        make_trainer("trainer_off", active=False)
        r = self.client.post(reverse("accounts:login"), {"identifier": "trainer_off", "password": "trainer12345"})
        self.assertContains(r, "Username atau Password Salah")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_anonymous_redirected_to_login(self):
        r = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("accounts:login"), r["Location"])

    def test_trainer_cannot_open_admin_pages(self):
        self.client.login(username="trainer_dedi", password="trainer12345")
        r = self.client.get(reverse("accounts:user_list"))
        self.assertRedirects(r, reverse("dashboard:trainer"), fetch_redirect_response=False)

    def test_logout_requires_post(self):
        self.client.login(username="admin", password="admin12345")
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class UserManagementTests(TestCase):
    def setUp(self):
        make_admin()
        self.client.login(username="admin", password="admin12345")
        self.valid = {"nama_lengkap": "Maya Putri", "username": "trainer_maya", "email": "maya@x.com",
                      "password": "rahasia123", "is_active": "on"}

    def test_create_trainer(self):
        r = self.client.post(reverse("accounts:user_add"), self.valid, follow=True)
        self.assertContains(r, "Data berhasil ditambahkan")
        u = User.objects.get(username="trainer_maya")
        self.assertEqual(u.role, User.Role.TRAINER)
        self.assertTrue(u.check_password("rahasia123"))
        self.assertTrue(AuditLog.objects.filter(aktivitas="Tambah data", objek="Akun Trainer").exists())

    def test_empty_fields_error(self):
        r = self.client.post(reverse("accounts:user_add"), {"is_active": "on"})
        self.assertContains(r, "Isi data dengan lengkap")
        self.assertFalse(User.objects.filter(role="TRAINER").exists())

    def test_invalid_email_format(self):
        r = self.client.post(reverse("accounts:user_add"), {**self.valid, "email": "bukan-email"})
        self.assertContains(r, "Gunakan format email dengan benar")

    def test_duplicate_username_and_email(self):
        make_trainer("trainer_maya")
        r = self.client.post(reverse("accounts:user_add"), self.valid)
        self.assertContains(r, "Username sudah digunakan")

    def test_edit_without_password_keeps_old_password(self):
        t = make_trainer("trainer_x", name="Lama")
        data = {**self.valid, "username": "trainer_x", "email": "trainer_x@x.com", "password": "", "nama_lengkap": "Baru"}
        self.client.post(reverse("accounts:user_edit", args=[t.pk]), data)
        t.refresh_from_db()
        self.assertEqual(t.first_name, "Baru")
        self.assertTrue(t.check_password("trainer12345"))

    def test_toggle_status(self):
        t = make_trainer("trainer_x")
        self.client.post(reverse("accounts:user_toggle", args=[t.pk]))
        t.refresh_from_db()
        self.assertFalse(t.is_active)


class AuditLogTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.dedi = make_trainer()
        self.client.login(username="admin", password="admin12345")
        log(self.dedi, "Input data", "Capaian harian", "TR-0142 output 118")
        log(self.admin, "Ubah data", "Master proses", "PRC-003 target 180 → 200")

    def test_list_and_filter_by_trainer(self):
        r = self.client.get(reverse("accounts:audit_log"), {"trainer": "trainer_dedi"})
        self.assertContains(r, "TR-0142 output 118")
        self.assertNotContains(r, "PRC-003 target")

    def test_filter_by_date_range_empty_message(self):
        old = (timezone.localdate() - timedelta(days=30)).isoformat()
        r = self.client.get(reverse("accounts:audit_log"), {"dari": old, "sampai": old})
        self.assertContains(r, "Data tidak ditemukan")

    def test_log_is_immutable(self):
        entry = AuditLog.objects.first()
        entry.keterangan = "diubah"
        with self.assertRaises(PermissionError):
            entry.save()
        with self.assertRaises(PermissionError):
            entry.delete()
