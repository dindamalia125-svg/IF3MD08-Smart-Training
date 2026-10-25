---

## tags: [aturan-bisnis, STA] updated: 2026-10-25

# Aturan Bisnis

Kembali ke [[00 AI Context]]. Alur per fitur ada di [[02 Use Case]].

## Angka yang bisa diatur (env, lihat `config/settings.py`)

|Aturan|Default|Variabel|Dipakai di|
|---|---|---|---|
|Qualified bila rata-rata output ≥ X × target|0.9|`QUALIFY_THRESHOLD`|`training/evaluasi.py`|
|Peringatan bila lama training ≥ X × durasi maks|0.9|`TRAINING_WARNING_RATIO`|`dashboard/views.py::trainer`|
|Notifikasi kontrak bila berakhir ≤ N hari|30|`CONTRACT_WARNING_DAYS`|`dashboard/views.py::trainer`|

## Kualifikasi

- Rata-rata dihitung dari `Capaian` dengan `aktif=True` untuk pasangan trainee+proses, dibulatkan.
- Rekomendasi `True` hanya bila **ada minimal satu hari capaian** dan rata-rata ≥ target × threshold.
- Contoh: target 120, threshold 0.9 → butuh rata-rata ≥ 108.
- Rekomendasi hanyalah saran. Trainer wajib memilih "Setuju" sebelum sertifikat dibuat.
- Status label trainee: "Qualified" bila **minimal satu** proses `QUALIFIED`, selain itu "Dalam training".
- `tanggal_qualified` diisi sekali (tidak ditimpa bila sudah ada).

## Capaian

- `output` dan `reject` bilangan bulat ≥ 0.
- Satu data aktif per trainee + proses + tanggal. Penimpaan wajib konfirmasi.
- Data lama **tidak pernah dihapus**: `aktif=False`. Semua agregasi (dashboard, evaluasi, laporan, progress) memfilter `aktif=True`.
- `persen_target` = output / target harian × 100 (0 bila target 0).
- Bila `ProsesTrainee` belum ada saat input capaian, dibuat dengan `mulai` = tanggal capaian.

## Peringatan masa training (UC-12)

- Hanya `ProsesTrainee` berstatus TRAINING.
- `lama_hari` = hari ini − `mulai` (minimum 0).
- Rasio = lama_hari / durasi_maks_hari. Tampil bila rasio ≥ threshold. Rasio ≥ 1 → "melewati batas".
- `durasi_maks_hari` 0 → tidak ada peringatan (hindari bagi nol).

## Kontrak (UC-13)

- Trainee `aktif=True`, `kontrak_berakhir` di antara hari ini dan hari ini + N hari. Kontrak yang sudah lewat **tidak** muncul.
- Lokasi = `Lini.lokasi_lengkap` + nama proses pertama trainee.

## Sertifikat

- Nomor: `CERT-<tahun>-<urut 4 digit>`, urutan dihitung dari nomor terakhir pada tahun itu (`Sertifikat.nomor_berikutnya`).
- Satu sertifikat per proses yang lolos dan disetujui, dalam satu transaksi.
- Urutan dalam `transaction.atomic`: buat sertifikat → set QUALIFIED → uji bangun PDF. Gagal di mana pun → semua dibatalkan.
- Audit log dicatat **setelah** commit.
- Mencetak ulang proses yang sama membuat sertifikat **baru** dengan nomor baru (belum ada pencegahan duplikat).
- Template PDF: A4 landscape, logo/QR masih placeholder, tanda tangan "Trainer" dan "Super Admin".

## Manpower

- Kode shift valid = isi tabel `Shift`; pencocokan tidak membedakan huruf besar/kecil dan dinormalkan ke kode resmi.
- Employee No dinormalkan huruf besar. Duplikat = sudah ada di database **atau** kembar di daftar yang sama (yang pertama menang).
- Trainee baru: `mulai_training` = hari ini, plus satu `RiwayatShift`. `lini` dan `kontrak_berakhir` **belum** diisi lewat parsing (diatur manual, mis. lewat admin).
- Hasil AI/regex adalah rekomendasi. Baris `gagal`/`duplikat` ditolak saat simpan.
- Batas `.docx`: 5 MB; teks dipotong 20.000 karakter sebelum diparse. Baris judul tabel dilewati.
- Bila API Anthropic gagal (timeout, error jaringan, JSON tidak valid), otomatis pakai parser regex; sumber ditampilkan di halaman.

## Audit log

Nilai `aktivitas` yang sah (`AuditLog.AKTIVITAS`): Tambah data, Ubah data, Input data, Parsing manpower, Cetak sertifikat, Ekspor laporan. Penghapusan master dicatat sebagai "Ubah data". Keterangan dipotong 300 karakter.

## Laporan

- Hanya `Capaian` aktif pada periode.
- Dikelompokkan per trainee + proses: total output, total reject, jumlah hari.
- % Target = total output / (target × jumlah hari). Di xlsx disimpan sebagai pecahan dengan format `0%`.
- Nama file: `rekap_training_<tanggal>.<fmt>` (harian), `rekap_training_bulanan_<yyyy-mm>.<fmt>` (bulanan).

## Akses

|Fitur|Super Admin|Trainer|
|---|---|---|
|Akun Trainer, Master, Audit Log, Dashboard Admin|✔|✖|
|Manpower, Capaian, Penelusuran, Sertifikat, Laporan, Dashboard Trainer|✖|✔|

Django admin (`/admin/`) memakai izin Django terpisah; akun demo `superadmin` adalah staff dan superuser.