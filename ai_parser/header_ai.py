"""Bantuan AI (Claude) untuk mengenali header kolom dokumen recruitment.

Privasi: yang dikirim ke API hanya teks header kolom (mis. "Emp. No", "Sect/Dept"),
TIDAK ada nama atau nomor karyawan. Hasil AI hanya dipakai bila lolos pemeriksaan
(field harus termasuk daftar FIELDS) dan tidak menimpa pengenalan berbasis aturan.
Tanpa ANTHROPIC_API_KEY, atau bila panggilan gagal, fungsi mengembalikan {} dan
parser tetap berjalan dengan aturan saja.

Pengecualian: `extract_rows_with_ai` dipakai HANYA bila aturan tidak menemukan tabel sama sekali.
Fungsi ini mengirim isi dokumen (termasuk nama & Emp No) ke API agar AI membaca dokumen otomatis.
Hasilnya tetap divalidasi aturan deterministik dan harus dikonfirmasi pengguna di preview.
"""
import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

FIELDS = (
    "employee_number", "employee_name", "gender", "department",
    "shift", "position", "status", "remarks",
)
FIELD_HELP = (
    "employee_number = nomor karyawan (Emp No / NIK); employee_name = nama karyawan; gender = jenis kelamin; "
    "department = Sect/Dept (kode dan nama section, mis. '2700 / Haemo'); shift; position = jabatan; "
    "status = status kepegawaian (kontrak/tetap); remarks = keterangan/replacement."
)


def _call_claude(labels):
    prompt = (
        "Berikut teks header kolom sebuah tabel recruitment karyawan, urut dari indeks 0. "
        f"Petakan tiap header ke salah satu field: {', '.join(FIELDS)}. Arti field: {FIELD_HELP} "
        'Header yang tidak cocok (mis. "No.") diabaikan. Balas HANYA JSON object berbentuk '
        '{"<indeks>": "<field>"}.\n\n' + json.dumps(labels, ensure_ascii=False)
    )
    body = json.dumps({
        "model": settings.ANTHROPIC_MODEL, "max_tokens": 500,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"content-type": "application/json", "x-api-key": settings.ANTHROPIC_API_KEY,
                 "anthropic-version": "2023-06-01"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())
    out = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return re.sub(r"^```(?:json)?|```$", "", out.strip(), flags=re.M).strip()


def map_headers_with_ai(labels):
    """labels: list teks header -> {indeks(int): field}. {} bila AI tidak tersedia/gagal."""
    if not settings.ANTHROPIC_API_KEY:
        return {}
    try:
        raw = json.loads(_call_claude(labels))
        if not isinstance(raw, dict):
            raise ValueError("Respons AI bukan object JSON")
        result = {}
        for key, field in raw.items():
            if str(key).isdigit() and field in FIELDS and 0 <= int(key) < len(labels):
                result[int(key)] = field
        return result
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
        logger.warning("Pemetaan header oleh AI gagal (%s: %s); memakai aturan saja.", type(exc).__name__, exc)
        return {}


ROW_KEYS = ("employee_number", "employee_name", "gender", "department", "shift", "position", "status", "remarks")
MAX_AI_ROWS = 500


def _call_claude_extract(text):
    prompt = (
        "Berikut isi dokumen recruitment karyawan (bisa berupa tabel, daftar, atau teks bebas). "
        "Ekstrak SETIAP karyawan baru menjadi JSON array of object dengan kunci: "
        f"{', '.join(ROW_KEYS)}. {FIELD_HELP} "
        "Tulis department persis seperti di dokumen (mis. '2700 / Haemo'). Jangan mengarang data: "
        "bagian yang tidak ada diisi string kosong. Abaikan baris judul/header/tanda tangan. "
        "Balas HANYA JSON array.\n\n" + text
    )
    body = json.dumps({
        "model": settings.ANTHROPIC_MODEL, "max_tokens": 8000,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"content-type": "application/json", "x-api-key": settings.ANTHROPIC_API_KEY,
                 "anthropic-version": "2023-06-01"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    out = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return re.sub(r"^```(?:json)?|```$", "", out.strip(), flags=re.M).strip()


def extract_rows_with_ai(text):
    """Teks dokumen -> list baris mentah (kunci ROW_KEYS + source_row). [] bila AI tidak tersedia/gagal."""
    if not settings.ANTHROPIC_API_KEY or not text.strip():
        return []
    try:
        items = json.loads(_call_claude_extract(text))
        if not isinstance(items, list):
            raise ValueError("Respons AI bukan array JSON")
        rows = []
        for number, item in enumerate(items[:MAX_AI_ROWS], start=1):
            if isinstance(item, dict):
                rows.append({**{k: str(item.get(k) or "").strip() for k in ROW_KEYS}, "source_row": number})
        return rows
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
        logger.warning("Pembacaan dokumen oleh AI gagal (%s: %s).", type(exc).__name__, exc)
        return []
