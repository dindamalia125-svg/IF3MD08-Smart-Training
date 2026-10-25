# Changelog

## 2026-10-25
- Membuat vault Obsidian sebagai konteks untuk AI agent.
- UC-02: field Email pada form Tambah/Ubah Akun Trainer diganti Employee No (unik). Kolom `employee_no` ditambahkan ke `User` (migrasi `0002_employee_no`); `email` kini opsional. Login menerima username, email, atau Employee No; pencarian pengguna memakai Employee No.
