# Status & TODO

## Sedang dikerjakan
- (kosong)

## Selesai
- Input Manpower (AI): area drag & drop file Word/PDF (`partials/dropzone.html`, `static/js/dropzone.js`); dokumen diparsing, dipisah per Sect/Dept, dan hanya 2700 / Haemo yang diimpor setelah konfirmasi preview
- AI Parser upload Word (`/manpower/upload/`): AI hanya membantu mengenali header, validasi tetap aturan deterministik, simpan hanya setelah konfirmasi preview (tes `ai_parser`)
- UC-01 s.d. UC-13 sudah diimplementasikan (51 tes)
- UC-02: form Tambah/Ubah Akun Trainer memakai Emp No. (menggantikan Email)

## TODO
- [ ] Uji panggilan Claude sungguhan untuk pemetaan header dengan `ANTHROPIC_API_KEY` (tes saat ini memakai AI tiruan)
- [ ] PDF hasil scan (butuh OCR, mis. PaddleOCR) belum didukung; PDF digital sudah (pypdf)
- [ ] `training/file_reader.py` belum dipanggil dari mana pun (jalur teks `/trainer/manpower/`)
- [ ] Jalur teks `/trainer/manpower/` (Trainee) dan jalur upload Word (Manpower) masih terpisah
- [ ] Perbaiki `login.html`: pesan "Username atau Password Salah" tidak tampil
- [ ] Aktifkan link "Lupa kata sandi?"
- [ ] Batasi akses `sertifikat_pdf`
- [ ] Hapus duplikat `show_form =show_form =`