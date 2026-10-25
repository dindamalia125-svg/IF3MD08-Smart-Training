# IF3MD08 — Smart Training Analytics Platform (Django)

Implementasi wireframe + activity diagram **STA** (UC-01 s.d. UC-13) menggunakan Django 5.

## Menjalankan
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo          # data contoh (opsional, aman diulang)
python manage.py runserver
```
Buka http://127.0.0.1:8000 .

| Peran | Username | Password |
|---|---|---|
| Super Admin | `superadmin` | `admin12345` |
| Trainer | `trainer_dedi` / `trainer_sari` | `trainer12345` |
| Trainer nonaktif (uji login ditolak) | `trainer_budi` | `trainer12345` |

> Akun demo hanya untuk pengembangan. Ganti semua password dan `DJANGO_SECRET_KEY`, set `DJANGO_DEBUG=0` dan `DJANGO_ALLOWED_HOSTS` di produksi.

Tes otomatis: `python manage.py test` (46 tes).

## Pemetaan Use Case → URL → kode
| UC | Layar wireframe | URL | Kode utama |
|---|---|---|---|
| UC-01 | Login | `/masuk/` | `accounts/views.py::login_view` |
| UC-02 | Manajemen Pengguna | `/pengguna/` | `accounts/views.py::user_list`, `forms.TrainerForm` |
| UC-03 | Master Proses | `/master/proses/` | `master/views.py::proses_list` |
| UC-04 | Master Shift & Lini | `/master/shift-lini/` | `master/views.py::shift_lini` |
| UC-05 | Audit Log | `/audit-log/` | `accounts/views.py::audit_log`, `models.AuditLog` |
| UC-06 | Dashboard Super Admin | `/dashboard/admin/` | `dashboard/views.py::super_admin` |
| UC-07 | Parsing Manpower AI | `/trainer/manpower/` | `training/views.py::manpower`, `training/ai_parser.py` |
| UC-08 | Input Capaian Harian | `/trainer/capaian/` | `training/views.py::capaian` |
| UC-09 | Penelusuran Trainee | `/trainer/penelusuran/` | `training/views.py::penelusuran`, `trainee_profil` |
| UC-10 | Evaluasi & Cetak Sertifikat | `/trainer/trainee/<id>/evaluasi/` | `training/views.py::evaluasi`, `evaluasi.py`, `pdf.py` |
| UC-11 | Ekspor Laporan | `/laporan/` | `reports/views.py`, `reports/services.py` |
| UC-12/13 | Dashboard Trainer | `/dashboard/trainer/` | `dashboard/views.py::trainer` |

## Cabang alternatif activity diagram yang diimplementasikan
- **UC-01** kredensial salah / akun Trainer nonaktif → "Username atau Password Salah".
- **UC-02/03/04** kolom kosong, format email salah, kode/akun duplikat → pesan kesalahan; berhasil → konfirmasi + audit log.
- **UC-05** tidak ada aktivitas pada filter → "Data tidak ditemukan". Audit log tidak bisa diubah/dihapus.
- **UC-06** data kosong → dashboard kosong dengan keterangan.
- **UC-07** teks kosong → diminta menempel data; baris gagal parsing ditandai; Employee No duplikat ditolak saat simpan.
- **UC-08** isian bukan angka / negatif → error; capaian sudah ada → konfirmasi timpa (riwayat lama disimpan, `aktif=False`).
- **UC-09** tidak ditemukan → pesan; lebih dari satu hasil → daftar untuk dipilih.
- **UC-10** tidak disetujui / belum qualified → tombol Cetak nonaktif (divalidasi juga di server); PDF gagal → pesan + bisa coba lagi (transaksi di-rollback).
- **UC-11** periode kosong / tanpa data → pesan, file tidak dibuat.
- **UC-12/13** tanpa operator mendekati batas / tanpa kontrak habis → tidak ada notifikasi.

## Modul AI (UC-07)
Set `ANTHROPIC_API_KEY` (opsional `ANTHROPIC_MODEL`) agar teks diparsing oleh Claude. Tanpa kunci, dipakai parser berbasis aturan sebagai fallback. Hasil selalu berupa rekomendasi yang bisa diperbaiki Trainer sebelum disimpan.

## Pengaturan yang dapat diubah (env)
`QUALIFY_THRESHOLD` (default 0.9 — rata-rata output ≥ 90% target = Qualified), `TRAINING_WARNING_RATIO` (0.9), `CONTRACT_WARNING_DAYS` (30).

## Catatan
- Basis data default SQLite; ganti `DATABASES` di `config/settings.py` untuk PostgreSQL/MySQL.
- Chart.js dimuat dari CDN pada dashboard Super Admin.
- Rekomendasi kualifikasi (UC-10) saat ini berbasis aturan (`training/evaluasi.py`); dapat diganti pemanggilan model AI tanpa mengubah view.
