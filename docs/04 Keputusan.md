# Keputusan

## 2026-10-25: Capaian tidak dihapus
Saat ditimpa, data lama ditandai `aktif=False`. Alasan: activity diagram UC-08
mewajibkan riwayat tetap tersimpan.

## 2026-10-25: Employee No menggantikan Email pada akun Trainer
Form UC-02 meminta Employee No, bukan Email. Kolom `email` tetap ada di model tetapi
opsional (NULL), sehingga akun lama tetap bisa login dengan email.