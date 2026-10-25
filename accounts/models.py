from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils import timezone


class User(AbstractUser):
    """Aktor sistem: Super Admin dan Trainer (UC-01, UC-02)."""

    class Role(models.TextChoices):
        SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"
        TRAINER = "TRAINER", "Trainer"

    email = models.EmailField("email", unique=True, null=True, blank=True)
    employee_no = models.CharField("Employee No", max_length=30, unique=True, null=True, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.TRAINER)

    def save(self, *args, **kwargs):
        # string kosong -> NULL agar kolom unik tidak bentrok antar akun tanpa email / Employee No
        self.email = self.email or None
        self.employee_no = self.employee_no or None
        super().save(*args, **kwargs)

    @property
    def is_super_admin(self):
        return self.role == self.Role.SUPER_ADMIN

    @property
    def is_trainer(self):
        return self.role == self.Role.TRAINER

    @property
    def nama_tampil(self):
        return self.get_full_name() or self.username

    @property
    def home_url(self):
        return reverse("dashboard:super_admin" if self.is_super_admin else "dashboard:trainer")

    def __str__(self):
        return self.username


class AuditLog(models.Model):
    """Riwayat aktivitas sistem (UC-05). Hanya boleh ditambah; tidak dapat diubah atau dihapus."""

    AKTIVITAS = [
        "Tambah data",
        "Ubah data",
        "Input data",
        "Parsing manpower",
        "Cetak sertifikat",
        "Ekspor laporan",
    ]

    waktu = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs")
    username = models.CharField(max_length=150, blank=True)
    aktivitas = models.CharField(max_length=60, db_index=True)
    objek = models.CharField(max_length=80)
    keterangan = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-waktu", "-id"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("Audit log bersifat permanen dan tidak dapat diubah.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit log bersifat permanen dan tidak dapat dihapus.")

    def __str__(self):
        return f"{self.waktu:%Y-%m-%d %H:%M} {self.username} {self.aktivitas}"
