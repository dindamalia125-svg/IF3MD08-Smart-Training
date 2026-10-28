"""Parser dokumen recruitment PDF (digital) untuk Manpower.

PDF digital dibaca dengan pypdf: satu baris tabel = satu karyawan. Baris dikenali dari pola
`[No] <Emp No> <Nama> [Gender] <Kode / Section> <Shift> <Position> <Status> <Replacement>`.
Hasilnya diteruskan ke `build_result` yang sama dengan jalur Word, sehingga filter 2700 / Haemo,
validasi, dan duplikasi memakai aturan deterministik yang sama.

PDF hasil scan (gambar) tidak berisi teks dan belum didukung (butuh OCR); pengguna diberi pesan jelas.
"""
from __future__ import annotations

import logging
import re

from pypdf import PdfReader

from .word_parser import build_result, clean, extract_join_date_from_text

logger = logging.getLogger(__name__)

MAX_PAGES = 50
GENDER = r"(?:Male|Female|Pria|Wanita|Laki-laki|Perempuan)"
# Sect/Dept: kode angka + pemisah + nama satu kata, mis. "2700 / Haemo", "1340 / Tech4"
DEPT_TOKEN = r"\d{3,5}\s*[/\-–—:|]\s*[A-Za-z][A-Za-z0-9]*"
ROW_START_RE = re.compile(r"^\s*\d{1,4}\s+[A-Za-z]{0,3}\d{4,8}\s+\S")
ROW_RE = re.compile(
    rf"^\s*(?P<no>\d{{1,4}})\s+(?P<emp>[A-Za-z]{{0,3}}\d{{4,8}})\s+(?P<name>.+?)\s+"
    rf"(?:(?P<gender>{GENDER})\s+)?(?P<dept>{DEPT_TOKEN})\s*(?P<rest>.*)$",
    re.I,
)
SHIFT_RE = re.compile(r"^(Normal|Non-?\s?shift|[A-C]|\d+\s?x\s?\d+)\b\s*", re.I)
STATUS_RE = re.compile(r"\b(Contract|Permanent|Kontrak|Tetap|Probation|Trainee|Outsourcing|Magang)\b", re.I)


def _split_rest(rest: str):
    """'Normal Operator Contract Additional' -> (shift, position, status, remarks)."""
    rest = clean(rest)
    shift = position = status = remarks = ""
    match = SHIFT_RE.match(rest)
    if match:
        shift, rest = clean(match.group(1)), rest[match.end():]
    match = STATUS_RE.search(rest)
    if match:
        position, status, remarks = clean(rest[:match.start()]), match.group(1), clean(rest[match.end():])
    else:
        position = clean(rest)
    return shift, position, status, remarks


def _logical_rows(lines: list[str]) -> list[str]:
    """Gabungkan baris tabel yang terpotong ke baris berikutnya (mis. nama panjang)."""
    rows: list[str] = []
    current = None
    for line in lines:
        if ROW_START_RE.match(line):
            if current is not None:
                rows.append(current)
            current = line.strip()
        elif current is not None and not re.search(DEPT_TOKEN, current):
            current += " " + line.strip()  # lanjutan baris yang belum memuat Sect/Dept
        else:
            if current is not None:
                rows.append(current)
                current = None
    if current is not None:
        rows.append(current)
    return rows


def extract_pdf_text(file) -> str:
    try:
        reader = PdfReader(file)
        if reader.is_encrypted:
            raise ValueError("PDF dilindungi kata sandi. Buka proteksinya lalu unggah ulang.")
        if len(reader.pages) > MAX_PAGES:
            raise ValueError(f"PDF terlalu panjang (maks. {MAX_PAGES} halaman).")
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except ValueError:
        raise
    except Exception as exc:  # PdfReadError, EOFError, dll.
        logger.warning("PDF tidak dapat dibaca: %s: %s", type(exc).__name__, exc)
        raise ValueError("File PDF rusak atau tidak dapat dibaca.") from exc
    if not text.strip():
        raise ValueError("PDF tidak berisi teks (kemungkinan hasil scan/gambar). "
                         "Gunakan PDF digital atau dokumen Word (.docx).")
    return text


def parse_pdf(file) -> dict:
    text = extract_pdf_text(file)
    raw_rows = []
    for number, line in enumerate(_logical_rows(text.splitlines()), start=1):
        match = ROW_RE.match(clean(line))
        if not match:
            logger.info("Baris PDF tidak dikenali dan dilewati: %.80s", line)
            continue
        shift, position, status, remarks = _split_rest(match.group("rest"))
        raw_rows.append({
            "employee_number": match.group("emp"),
            "employee_name": clean(match.group("name")),
            "gender": clean(match.group("gender") or ""),
            "department": clean(match.group("dept")),
            "shift": shift, "position": position, "status": status, "remarks": remarks,
            "source_row": int(match.group("no")),
        })
    if not raw_rows:
        raise ValueError(
            "Baris karyawan tidak ditemukan pada PDF. Pastikan tabel berisi No, Emp. No, nama, dan Sect/Dept "
            "dalam satu baris, atau gunakan dokumen Word (.docx)."
        )
    return build_result(raw_rows, extract_join_date_from_text(text), "aturan", [])
