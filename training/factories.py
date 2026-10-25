"""Pembantu pembuatan data (dipakai tes dan perintah seed_demo)."""
from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from master.models import Lini, Proses, Shift
from training.models import Capaian, ProsesTrainee, RiwayatShift, Trainee


def make_admin(username="admin", password="admin12345"):
    return User.objects.create_user(username=username, email=f"{username}@x.com", password=password,
                                    role=User.Role.SUPER_ADMIN, first_name="Super Admin")


def make_trainer(username="trainer_dedi", password="trainer12345", active=True, name="Dedi Kurniawan"):
    return User.objects.create_user(username=username, email=f"{username}@x.com", password=password,
                                    role=User.Role.TRAINER, first_name=name, is_active=active,
                                    emp_no="EM-0001" if username == "trainer_dedi" else None)


def make_master():
    shifts = {k: Shift.objects.get_or_create(kode=k, defaults={"nama": n})[0]
              for k, n in {"3x2": "Shift 3x2", "A": "Shift A (pagi)", "B": "Shift B (siang)", "C": "Shift C (malam)"}.items()}
    linis = {n: Lini.objects.get_or_create(nama=n, defaults={"lokasi": l})[0]
             for n, l in {"Line 1": "Gedung A Lt.1", "Line 2": "Gedung A Lt.2", "Line 3": "Gedung B Lt.1"}.items()}
    proses = {k: Proses.objects.get_or_create(kode=k, defaults={"nama": n, "target_harian": t, "durasi_maks_hari": d})[0]
              for k, (n, t, d) in {"PRC-001": ("Assembly A", 120, 14), "PRC-002": ("Assembly B", 100, 14),
                                   "PRC-003": ("Inspeksi", 200, 10), "PRC-004": ("Packing", 300, 7),
                                   "PRC-005": ("Soldering", 80, 21)}.items()}
    return shifts, linis, proses


def make_trainee(emp_no="TR-0142", nama="Andi Pratama", shift=None, lini=None, **kw):
    t = Trainee.objects.create(emp_no=emp_no, nama=nama, shift=shift, lini=lini, **kw)
    if shift:
        RiwayatShift.objects.create(trainee=t, shift=shift, lini=lini, mulai=timezone.localdate() - timedelta(days=30))
    return t


def add_capaian(trainee, proses, outputs, user=None, reject=2):
    """outputs: daftar output per hari, dari kemarin mundur."""
    today = timezone.localdate()
    ProsesTrainee.objects.get_or_create(trainee=trainee, proses=proses, defaults={"mulai": today - timedelta(days=len(outputs))})
    for i, out in enumerate(outputs, start=1):
        Capaian.objects.create(trainee=trainee, proses=proses, tanggal=today - timedelta(days=i), output=out,
                               reject=reject, dicatat_oleh=user)
