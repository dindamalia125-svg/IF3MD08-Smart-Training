---

## tags: [use-case, STA] updated: 2026-10-25

# Use Case

Kembali ke [[00 AI Context]]. Aturan angka ada di [[03 Aturan Bisnis]].

## Pemetaan UC → URL → kode

|UC|Nama|Aktor|URL|Kode utama|Template|
|---|---|---|---|---|---|
|UC-01|Login|Semua|`/masuk/`|`accounts/views.py::login_view`|`accounts/login.html`|
|UC-02|Manajemen Akun Trainer|Super Admin|`/pengguna/`|`accounts/views.py::user_list`, `forms.TrainerForm`|`accounts/user_list.html`|
|UC-03|Master Proses|Super Admin|`/master/proses/`|`master/views.py::proses_list`|`master/proses_list.html`|
|UC-04|Master Shift & Lini|Super Admin|`/master/shift-lini/`|`master/views.py::shift_lini`|`master/shift_lini.html`|
|UC-05|Audit Log|Super Admin|`/audit-log/`|`accounts/views.py::audit_log`, `models.AuditLog`|`accounts/audit_log.html`|
|UC-06|Dashboard Super Admin|Super Admin|`/dashboard/admin/`|`dashboard/views.py::super_admin`|`dashboard/super_admin.html`|
|UC-07|Parsing Manpower (AI)|Trainer|`/trainer/manpower/`|`training/views.py::manpower`, `ai_parser.py`, `docx_reader.py`|`training/manpower.html`|
|UC-08|Input Capaian Harian|Trainer|`/trainer/capaian/`|`training/views.py::capaian`, `forms.CapaianForm`|`training/capaian.html`|
|UC-09|Penelusuran Trainee|Trainer|`/trainer/penelusuran/`|`training/views.py::penelusuran`, `trainee_profil`|`training/penelusuran.html`, `profil.html`|
|UC-10|Evaluasi & Cetak Sertifikat|Trainer|`/trainer/trainee/<id>/evaluasi/`|`training/views.py::evaluasi`, `evaluasi.py`, `pdf.py`|`training/evaluasi.html`|
|UC-11|Ekspor Laporan|Trainer|`/laporan/`|`reports/views.py`, `reports/services.py`|`reports/ekspor.html`|
|UC-12|Peringatan Masa Training|Trainer|`/dashboard/trainer/`|`dashboard/views.py::trainer`|`dashboard/trainer.html`|
|UC-13|Notifikasi Finish Kontrak|Trainer|`/dashboard/trainer/`|`dashboard/views.py::trainer`|`dashboard/trainer.html`|

URL tambahan: `/keluar/` (POST), `/pengguna/tambah/`, `/pengguna/<id>/ubah/`, `/pengguna/<id>/status/`, `/master/proses/tambah/`, `/master/proses/<id>/ubah/`, `/master/proses/<id>/hapus/`, `/master/shift/<id>/hapus/`, `/master/lini/<id>/hapus/`, `/trainer/sertifikat/`, `/trainer/sertifikat/pdf/?ids=1,2`, `/trainer/trainee/<id>/`, `/laporan/unduh/`.

## Ringkasan per UC dan cabang alternatif

### UC-01 Login

Identifier = username atau email. Akun nonaktif ditolak dengan pesan yang sama seperti password salah ("Username atau Password Salah"). Parameter `next` divalidasi dengan `url_has_allowed_host_and_scheme`. "Ingat saya" tidak dicentang → sesi berakhir saat browser ditutup.

### UC-02 Akun Trainer

Tambah/ubah/aktif-nonaktif. Password kosong saat ubah = tidak diganti. Username dan email unik (tanpa membedakan huruf besar/kecil). Validasi: kolom kosong, format email, minimal 8 karakter. Role selalu `TRAINER`.

### UC-03 Master Proses

Kode otomatis huruf besar dan unik. Target dan durasi harus angka ≥ 1. Ubah dicatat dengan diff ("target harian 180 → 200"). Hapus diblokir bila dipakai.

### UC-04 Master Shift & Lini

Dua form dalam satu halaman, dibedakan `form_type`. Kode shift dan nama lini unik. Hapus diblokir bila masih dipakai.

### UC-05 Audit Log

Filter tanggal, trainer, jenis aktivitas. Tidak ada hasil → "Data tidak ditemukan". Hanya tambah, tidak bisa ubah/hapus (juga di admin Django).

### UC-06 Dashboard Super Admin

KPI, grafik output dan reject harian, output per proses, 5 sertifikat terbaru. Filter periode bulanan (6 bulan terakhir). Hanya memakai `Capaian` dengan `aktif=True`.

### UC-07 Parsing Manpower

Input: teks atau `.docx` (file diutamakan bila keduanya ada). Tiap baris diberi status: `ok`, `gagal` (nama/badge/shift tidak lengkap atau shift tidak dikenal), `duplikat` (badge sudah ada atau kembar dalam daftar). Saat simpan, hanya baris `ok` yang masuk; data dikoreksi dulu oleh Trainer. Ditolak: bukan `.docx`, rusak, kosong, > 5 MB.

### UC-08 Capaian Harian

Output dan reject wajib bilangan bulat ≥ 0. Data aktif dengan trainee+proses+tanggal sama → minta konfirmasi timpa; yang lama `aktif=False`. `ProsesTrainee` dibuat otomatis pada input pertama. Progress = output terbaru / target harian.

### UC-09 Penelusuran

Cari badge atau nama. Satu hasil (atau badge persis) → langsung ke profil. Banyak → daftar pilih. Kosong → "Data trainee tidak ditemukan". Profil: riwayat shift dan proses.

### UC-10 Evaluasi & Sertifikat

Rekomendasi otomatis (rata-rata output vs target). Trainer memilih Setuju/Tidak per proses. Cetak hanya untuk proses yang direkomendasikan **dan** disetujui (dicek di JS dan di server). PDF gagal → rollback, bisa coba lagi.

### UC-11 Ekspor Laporan

Harian (satu tanggal) atau bulanan; format xlsx atau pdf. Alur: POST → redirect ke GET dengan `siap=1` → tombol Unduh. Periode kosong atau tanpa data → pesan, file tidak dibuat. Persentase = total output / (target × jumlah hari).

### UC-12 Peringatan Masa Training

Proses berstatus TRAINING dengan lama ≥ 90% durasi maks. Durasi 0 = diabaikan. Diurutkan dari persentase tertinggi; ≥ 100% ditandai "melewati batas".

### UC-13 Finish Kontrak

Trainee aktif dengan `kontrak_berakhir` dalam 30 hari ke depan. Menampilkan lini/lokasi, proses pertama, dan shift. Angka lonceng = peringatan UC-12 + notifikasi UC-13.

## Pengecualian akses

Trainer membuka halaman Super Admin (dan sebaliknya) → pesan "Anda tidak memiliki akses ke halaman tersebut." lalu redirect ke dashboard masing-masing.