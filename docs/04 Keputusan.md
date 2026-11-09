# Keputusan

## 2026-10-25: Capaian tidak dihapus
Saat ditimpa, data lama ditandai `aktif=False`. Alasan: activity diagram UC-08
mewajibkan riwayat tetap tersimpan.

## 2026-10-25: Employee No menggantikan Email pada akun Trainer
Form UC-02 meminta Employee No, bukan Email. Kolom `email` tetap ada di model tetapi
opsional (NULL), sehingga akun lama tetap bisa login dengan email.

## 2026-10-25: Penamaan "Emp No."
Label dan nama kolom database memakai `Emp No.` / `emp_no`, baik untuk akun Trainer (`User`) maupun trainee (`Trainee`). Commit sebelumnya tidak ditulis ulang; perubahan ditambahkan sebagai commit baru.


## 2026-11-09: AI boleh membaca isi dokumen bila tabel tidak dikenali
Sebelumnya AI hanya menerima teks header (tanpa data karyawan). Kini, hanya bila aturan tidak menemukan tabel sama sekali dan `ANTHROPIC_API_KEY` ada, isi dokumen (termasuk nama dan Emp No) dikirim ke API agar dokumen tetap terbaca otomatis. Keputusan data tetap oleh `validate_record` dan pengguna wajib konfirmasi di preview.
