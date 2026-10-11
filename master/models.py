from django.db import models


class Proses(models.Model):
    """Master proses kerja (UC-03): acuan target harian & durasi maksimal training."""

    kode = models.CharField("Kode Proses", max_length=20, unique=True)
    nama = models.CharField("Nama Proses", max_length=100)
    target_harian = models.PositiveIntegerField("Target Harian")
    durasi_maks_hari = models.PositiveIntegerField("Durasi Maks. Training (hari)")

    class Meta:
        ordering = ["kode"]
        verbose_name_plural = "proses"

    def __str__(self):
        return f"{self.kode} - {self.nama}"


class Shift(models.Model):
    """Master shift (UC-04): 3x2, A, B, C."""

    kode = models.CharField("Kode Shift", max_length=10, unique=True)
    nama = models.CharField("Nama Shift", max_length=60)

    class Meta:
        ordering = ["kode"]

    def __str__(self):
        return self.kode


class Lini(models.Model):
    """Master lini kerja / lokasi lini produksi (UC-04)."""

    nama = models.CharField("Nama Lini", max_length=60, unique=True)
    lokasi = models.CharField("Lokasi Produksi", max_length=120)

    class Meta:
        ordering = ["nama"]
        verbose_name_plural = "lini"

    def __str__(self):
        return self.nama

    @property
    def lokasi_lengkap(self):
        return f"{self.nama} · {self.lokasi}"
