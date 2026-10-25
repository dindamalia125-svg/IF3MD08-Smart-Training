# Changelog

## 2026-10-25
- Membuat vault Obsidian sebagai konteks untuk AI agent.
- UC-02: field Email pada form Tambah/Ubah Akun Trainer diganti Employee No (unik). Kolom `employee_no` ditambahkan ke `User` (migrasi `0002_employee_no`); `email` kini opsional. Login menerima username, email, atau Employee No; pencarian pengguna memakai Employee No.
- Seluruh teks "Nomor Badge" / "No. Badge" / "Badge" pada antarmuka, PDF sertifikat, laporan, pesan, dan dokumen diganti menjadi "Employee No" (migrasi `training.0002_employee_no_label`). Nama field `Trainee.badge` di kode tidak diubah.
- Istilah "Employee No" diganti menjadi "Emp No." di seluruh antarmuka dan dokumen. Di database: kolom `accounts_user.employee_no` dan `training_trainee.badge` diganti namanya menjadi `emp_no` (migrasi `accounts.0003_rename_employee_no_emp_no` dan `training.0003_rename_badge_emp_no`, data tetap terjaga). Jalankan `python manage.py migrate`.
