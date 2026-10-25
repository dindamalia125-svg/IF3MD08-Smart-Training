from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.audit import log
from accounts.models import User
from training.factories import add_capaian, make_master, make_trainee
from training.models import ProsesTrainee, Sertifikat, Trainee


class Command(BaseCommand):
    help = "Mengisi data demo (akun, master, trainee, capaian, sertifikat). Aman dijalankan berulang."

    def handle(self, *args, **opts):
        today = timezone.localdate()
        admin, _ = User.objects.get_or_create(username="superadmin", defaults={
            "email": "superadmin@perusahaan.com", "role": User.Role.SUPER_ADMIN, "first_name": "Super Admin",
            "is_staff": True, "is_superuser": True})
        admin.set_password("admin12345")
        admin.save()
        trainers = []
        for uname, nama, no in (("trainer_dedi", "Dedi Kurniawan", "EM-0001"), ("trainer_sari", "Sari Utami", "EM-0002"),
                                ("trainer_budi", "Budi Santoso", "EM-0003")):
            u, _ = User.objects.get_or_create(username=uname, defaults={
                "email": f"{uname.split('_')[1]}@perusahaan.com", "first_name": nama, "role": User.Role.TRAINER, "employee_no": no,
                "is_active": uname != "trainer_budi"})
            u.set_password("trainer12345")
            u.save()
            trainers.append(u)
        dedi, sari = trainers[0], trainers[1]
        shifts, linis, proses = make_master()

        if Trainee.objects.exists():
            self.stdout.write("Data trainee sudah ada, seed dilewati. Hapus db.sqlite3 untuk mengulang dari awal.")
            return

        def mk(badge, nama, shift, lini, **kw):
            return make_trainee(badge, nama, shifts[shift], linis[lini], mulai_training=today - timedelta(days=20), **kw)

        andi = mk("TR-0142", "Andi Pratama", "A", "Line 2", kontrak_berakhir=today + timedelta(days=120))
        maya = mk("TR-0098", "Maya Putri", "B", "Line 1", kontrak_berakhir=today + timedelta(days=200))
        rudi = mk("TR-0177", "Rudi Hartono", "3x2", "Line 3", kontrak_berakhir=today + timedelta(days=90))
        sinta = mk("TR-0204", "Sinta Dewi", "A", "Line 1", kontrak_berakhir=today + timedelta(days=150))
        hasan = mk("TR-0215", "Hasan Basri", "B", "Line 2", kontrak_berakhir=today + timedelta(days=160))
        siti = mk("EM-0211", "Siti Rahma", "A", "Line 2", kontrak_berakhir=today + timedelta(days=14))
        joko = mk("EM-0305", "Joko Susilo", "B", "Line 1", kontrak_berakhir=today + timedelta(days=17))
        lia = mk("EM-0187", "Lia Anggraini", "3x2", "Line 3", kontrak_berakhir=today + timedelta(days=21))

        # capaian + proses (mulai training diatur agar muncul peringatan UC-12)
        add_capaian(andi, proses["PRC-001"], [118, 121, 110, 105, 98, 112, 120, 116, 113, 119, 115, 111, 114], dedi)
        add_capaian(andi, proses["PRC-004"], [296, 300, 292, 298, 295], dedi)
        add_capaian(andi, proses["PRC-003"], [140, 138, 142], sari)
        add_capaian(maya, proses["PRC-003"], [186, 190, 182, 195, 188, 185, 191, 184, 187], sari)
        add_capaian(rudi, proses["PRC-005"], [74, 72, 76, 71, 73] * 4, dedi)
        add_capaian(sinta, proses["PRC-004"], [298, 297, 299, 301, 296], dedi)
        add_capaian(hasan, proses["PRC-002"], [96, 98, 95, 97, 99], sari)
        for t, p in ((siti, "PRC-002"), (joko, "PRC-004"), (lia, "PRC-003")):
            ProsesTrainee.objects.create(trainee=t, proses=proses[p], mulai=today - timedelta(days=2))

        # status kelulusan & sertifikat contoh
        for t, p in ((andi, "PRC-004"), (sinta, "PRC-004")):
            pt = ProsesTrainee.objects.get(trainee=t, proses=proses[p])
            pt.status, pt.tanggal_qualified = ProsesTrainee.Status.QUALIFIED, today - timedelta(days=3)
            pt.save()
            Sertifikat.objects.create(nomor=Sertifikat.nomor_berikutnya(), trainee=t, proses=proses[p],
                                      dicetak_oleh=dedi, tanggal=today - timedelta(days=3), rata_output=297)

        log(sari, "Parsing manpower", "Data manpower", "8 baris disimpan, 1 baris ditolak (duplikat Employee No)")
        log(dedi, "Input data", "Capaian harian", "TR-0142 · Assembly A · output 118, reject 2")
        log(dedi, "Cetak sertifikat", "Sertifikat", "CERT-demo · Andi Pratama")
        log(admin, "Ubah data", "Master proses", "PRC-003 target harian 180 → 200")
        log(admin, "Tambah data", "Akun Trainer", "trainer_budi dibuat")
        self.stdout.write(self.style.SUCCESS(
            "Seed selesai. Login: superadmin / admin12345  |  trainer_dedi / trainer12345"))
