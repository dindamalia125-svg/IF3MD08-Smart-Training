from django.conf import settings
from django.db import models
from django.utils import timezone

from master.models import Lini, Proses, Shift


class Trainee(models.Model):
    """Karyawan/operator yang menjalani training (hasil UC-07)."""

    emp_no = models.CharField("Emp No.", max_length=30, unique=True)
    nama = models.CharField(max_length=150)
    shift = models.ForeignKey(Shift, null=True, blank=True, on_delete=models.SET_NULL, related_name="trainees")
    lini = models.ForeignKey(Lini, null=True, blank=True, on_delete=models.SET_NULL, related_name="trainees")
    kontrak_berakhir = models.DateField(null=True, blank=True)
    mulai_training = models.DateField(null=True, blank=True)
    aktif = models.BooleanField(default=True)
    dibuat = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nama"]

    def __str__(self):
        return f"{self.emp_no} {self.nama}"

    @property
    def status_label(self):
        has_q = self.proses_list.filter(status=ProsesTrainee.Status.QUALIFIED).exists()
        return "Qualified" if has_q else "Dalam training"


class RiwayatShift(models.Model):
    trainee = models.ForeignKey(Trainee, on_delete=models.CASCADE, related_name="riwayat_shift")
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT)
    lini = models.ForeignKey(Lini, null=True, blank=True, on_delete=models.SET_NULL)
    mulai = models.DateField()
    selesai = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-mulai"]


class ProsesTrainee(models.Model):
    """Proses yang diikuti/dikuasai seorang trainee beserta status kelulusannya."""

    class Status(models.TextChoices):
        TRAINING = "TRAINING", "Dalam training"
        QUALIFIED = "QUALIFIED", "Qualified"

    trainee = models.ForeignKey(Trainee, on_delete=models.CASCADE, related_name="proses_list")
    proses = models.ForeignKey(Proses, on_delete=models.PROTECT, related_name="peserta")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TRAINING)
    mulai = models.DateField(default=timezone.localdate)
    tanggal_qualified = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = [("trainee", "proses")]
        ordering = ["proses__kode"]

    def __str__(self):
        return f"{self.trainee.emp_no} · {self.proses.nama}"

    @property
    def lama_hari(self):
        return max((timezone.localdate() - self.mulai).days, 0)


class Capaian(models.Model):
    """Capaian harian (UC-08). Data lama tidak dihapus; saat ditimpa ditandai aktif=False."""

    trainee = models.ForeignKey(Trainee, on_delete=models.CASCADE, related_name="capaian")
    proses = models.ForeignKey(Proses, on_delete=models.PROTECT, related_name="capaian")
    tanggal = models.DateField()
    output = models.PositiveIntegerField("Output Konten")
    reject = models.PositiveIntegerField("Jumlah Reject", default=0)
    dicatat_oleh = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    dibuat = models.DateTimeField(auto_now_add=True)
    aktif = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-tanggal", "-dibuat"]
        indexes = [models.Index(fields=["trainee", "proses", "tanggal", "aktif"])]

    @property
    def persen_target(self):
        t = self.proses.target_harian
        return round(self.output / t * 100) if t else 0


class Sertifikat(models.Model):
    nomor = models.CharField(max_length=30, unique=True)
    trainee = models.ForeignKey(Trainee, on_delete=models.PROTECT, related_name="sertifikat")
    proses = models.ForeignKey(Proses, on_delete=models.PROTECT)
    tanggal = models.DateField(default=timezone.localdate)
    dicetak_oleh = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    rata_output = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-tanggal", "-id"]
        verbose_name_plural = "sertifikat"

    def __str__(self):
        return self.nomor

    @classmethod
    def nomor_berikutnya(cls, tahun=None):
        tahun = tahun or timezone.localdate().year
        prefix = f"CERT-{tahun}-"
        last = cls.objects.filter(nomor__startswith=prefix).order_by("-nomor").first()
        seq = int(last.nomor.rsplit("-", 1)[1]) + 1 if last else 1
        return f"{prefix}{seq:04d}"
