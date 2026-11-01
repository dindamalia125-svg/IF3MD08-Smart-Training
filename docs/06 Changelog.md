# Changelog

## 2026-10-25
- Membuat vault Obsidian sebagai konteks untuk AI agent.
- UC-02: field Email pada form Tambah/Ubah Akun Trainer diganti Employee No (unik). Kolom `employee_no` ditambahkan ke `User` (migrasi `0002_employee_no`); `email` kini opsional. Login menerima username, email, atau Employee No; pencarian pengguna memakai Employee No.
- Seluruh teks "Nomor Badge" / "No. Badge" / "Badge" pada antarmuka, PDF sertifikat, laporan, pesan, dan dokumen diganti menjadi "Employee No" (migrasi `training.0002_employee_no_label`). Nama field `Trainee.badge` di kode tidak diubah.
- Istilah "Employee No" diganti menjadi "Emp No." di seluruh antarmuka dan dokumen. Di database: kolom `accounts_user.employee_no` dan `training_trainee.badge` diganti namanya menjadi `emp_no` (migrasi `accounts.0003_rename_employee_no_emp_no` dan `training.0003_rename_badge_emp_no`, data tetap terjaga). Jalankan `python manage.py migrate`.

## 2026-10-29
- AI Parser upload Word: `split_department` menerima variasi penulisan Sect/Dept (`2700 - Haemo`, `2700/Haemo`, `Haemo / 2700`); validasi `2700 / Haemo` tetap ketat.
- Pesan file kosong pada form upload kini "File kosong." (sebelumnya tertimpa pesan bawaan Django).
- Menambah `LOGGING` (logger `ai_parser` ke konsol dan `logs/sta.log`); folder `logs/` masuk `.gitignore`.
- Memperbaiki tes `test_ai_cannot_override_rules_or_reuse_fields` (data AI tiruan tidak konsisten dengan hasil yang diharapkan). Tidak ada migrasi baru.
- Halaman Input Manpower (AI) dan Import Manpower: area drag & drop file Word (.docx) atau PDF digital (maks. 10 MB). File langsung diparsing, lalu preview menampilkan karyawan per section (2700 / Haemo diproses, section lain hanya ditampilkan dan tidak diimpor).
- `ai_parser/pdf_parser.py` (pypdf) baru; `word_parser.build_result` dipakai bersama oleh jalur Word dan PDF (validasi, filter section, duplikasi sama). PDF scan, terenkripsi, atau rusak ditolak dengan pesan jelas. Tidak ada migrasi baru.

