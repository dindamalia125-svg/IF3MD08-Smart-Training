---
tags: [ai-context, STA]
updated: 2026-10-25
---
# STA: Smart Training Analytics Platform (IF3MD08)

Aplikasi Django untuk mengelola training operator pabrik: input manpower,
capaian harian, evaluasi kualifikasi, sertifikat PDF, dan laporan.
Bahasa UI, nama model, dan nama field: **Bahasa Indonesia**.

## Stack
Django 5.2, SQLite, reportlab (PDF), openpyxl (Excel), python-docx,
Chart.js via CDN. Tanpa DRF/JS framework; template server-side.
AI: Anthropic API dipanggil lewat `urllib` (bukan SDK) di `training/ai_parser.py`,
model dari env `ANTHROPIC_MODEL`. Tanpa API key → fallback parser regex.

## Aktor & peran
- `SUPER_ADMIN`: master data, akun trainer, audit log, dashboard analitik.
- `TRAINER`: manpower, capaian, penelusuran, sertifikat, laporan.
Akses dibatasi dekorator `super_admin_required` / `trainer_required`
(`accounts/decorators.py`). User model kustom: `accounts.User`.

## Struktur app
| App | Isi |
|---|---|
| accounts | login, user Trainer, AuditLog |
| master | Proses, Shift, Lini |
| training | Trainee, ProsesTrainee, Capaian, Sertifikat, parsing, evaluasi, PDF |
| dashboard | dashboard Super Admin (UC-06) & Trainer (UC-12/13) |
| reports | ekspor rekap harian/bulanan xlsx/pdf (UC-11) |

## Konvensi WAJIB
1. Setiap view yang mengubah data memanggil `accounts.audit.log(user, aktivitas, objek, keterangan)`.
   Nilai `aktivitas` harus salah satu dari `AuditLog.AKTIVITAS`.
2. AuditLog **immutable** (save/delete ulang → PermissionError). Jangan dihapus.
3. Capaian tidak pernah dihapus: saat ditimpa, yang lama `aktif=False`.
   Semua query analitik harus memfilter `aktif=True`.
4. Pesan error/sukses dalam Bahasa Indonesia, sesuai teks di activity diagram
   (tes memeriksa string persisnya, jangan ubah sembarangan).
5. Halaman list+form memakai satu view untuk list/tambah/ubah
   (`proses_list`, `user_list`), dibedakan via `url_name`.
6. Data tes/seed lewat `training/factories.py`. Tes: `python manage.py test`.
7. Template memakai `novalidate`; validasi di server (Form Django).

## Aturan bisnis (angka bisa diubah via env)
- Qualified bila rata-rata output ≥ 90% target (`QUALIFY_THRESHOLD`).
- Peringatan training bila lama ≥ 90% durasi maks (`TRAINING_WARNING_RATIO`).
- Notifikasi kontrak bila berakhir ≤ 30 hari (`CONTRACT_WARNING_DAYS`).
- Nomor sertifikat: `CERT-<tahun>-<0001>`.
- Cetak sertifikat: dalam `transaction.atomic`; PDF harus sukses sebelum commit.
- Upload manpower: hanya `.docx`, maks 5 MB, teks dipotong 20.000 karakter.

## Menjalankan
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate && python manage.py seed_demo && python manage.py runserver
Akun demo: lihat README (hanya untuk dev).

## Hal yang perlu dicek / utang teknis
- `accounts/views.py` & `master/views.py`: ada `show_form =show_form =` (duplikat, tidak berbahaya).
- `login.html` memakai Bootstrap CDN, halaman lain memakai `static/css/app.css`.
- `login.html` hanya menampilkan pesan bila `form.errors`; variabel `error` dari view
  ("Username atau Password Salah") tidak dirender → cek tes login.
- Link "Lupa kata sandi?" masih `#`.
- `sertifikat_pdf` tidak memeriksa kepemilikan; semua Trainer bisa buka semua sertifikat.
- Chart.js dimuat dari CDN (butuh internet).

## Cara bekerja dengan saya (agent)
- Ubah seminimal mungkin, ikuti gaya kode yang ada.
- Setelah mengubah perilaku, perbarui tes dan `docs/06 Changelog.md`.
- Jangan menulis secret/API key ke file mana pun.

    ## Catatan terkait
    - [[01 Arsitektur]]
    - [[02 Use Case]]
    - [[03 Aturan Bisnis]]
    - [[04 Keputusan]]
    - [[05 Status & TODO]]
    - [[06 Changelog]]