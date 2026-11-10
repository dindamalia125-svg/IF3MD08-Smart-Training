"""Parser dokumen recruitment Word (.docx) untuk Manpower section 2700 / Haemo.

Pembagian tugas (sederhana dan aman):
- Aturan membaca tabel (termasuk tabel bersarang dan tabel teks berpemisah tab/|) lebih dulu.
- AI (opsional) membantu mengenali header kolom yang tidak dikenal (hanya teks header). Bila tidak
  ada tabel yang bisa dibaca sama sekali, AI membaca seluruh isi dokumen secara otomatis
  (`extract_rows_with_ai`) dan hasilnya tetap harus lolos validasi + konfirmasi preview.
- Semua keputusan data (filter 2700 / Haemo, field wajib, format Emp No, duplikat) dibuat
  oleh aturan deterministik di file ini, lewat `validate_record`.
"""
from __future__ import annotations

import logging
import re
from datetime import date

from django.conf import settings
from docx import Document

from .header_ai import FIELDS, extract_rows_with_ai, find_join_date_with_ai, map_headers_with_ai

logger = logging.getLogger(__name__)

TARGET_DEPT_CODE = "2700"
TARGET_DEPT_NAME = "haemo"
HEADER_SCAN_ROWS = 8  # header boleh berada di 8 baris pertama tabel (mis. ada baris judul/logo)
EMP_NO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]{2,29}$")
DEPT_SEPARATOR = r"(?:\s*[/\-–—:|]\s*|\s+)"  # "2700 / Haemo", "2700-Haemo", "2700 Haemo"
DEPT_RE = re.compile(rf"^\s*(\d+){DEPT_SEPARATOR}(.+?)\s*$")
DEPT_REVERSED_RE = re.compile(rf"^\s*(.+?){DEPT_SEPARATOR}(\d+)\s*$")  # "Haemo / 2700"
MAX_LEN = {"employee_name": 180, "position": 120, "status": 80, "remarks": 255, "shift": 50}
REQUIRED_HEADERS = {"employee_number", "employee_name", "department"}

ALIASES = {
    "empno": "employee_number",
    "employeeno": "employee_number",
    "employeenumber": "employee_number",
    "nomorkaryawan": "employee_number",
    "nik": "employee_number",
    "employeename": "employee_name",
    "empname": "employee_name",
    "nama": "employee_name",
    "namakaryawan": "employee_name",
    "gender": "gender",
    "jeniskelamin": "gender",
    "sectdept": "department",
    "sectiondepartment": "department",
    "sectiondept": "department",
    "section": "department",
    "departemen": "department",
    "department": "department",
    "shift": "shift",
    "position": "position",
    "jabatan": "position",
    "employmentstatus": "status",
    "status": "status",
    "doc": "doc",
    "dateofcommencement": "doc",
    "commencementdate": "doc",
    "joindate": "doc",
    "joiningdate": "doc",
    "tanggalmasuk": "doc",
    "tanggalbergabung": "doc",
    "replacement": "remarks",
    "remarks": "remarks",
    "keterangan": "remarks",
}


def canonical(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


# ----------------------------------------------------------------- tanggal DOC
MONTHS = {
    "jan": 1, "january": 1, "januari": 1, "feb": 2, "february": 2, "februari": 2, "mar": 3, "march": 3, "maret": 3,
    "apr": 4, "april": 4, "may": 5, "mei": 5, "jun": 6, "june": 6, "juni": 6, "jul": 7, "july": 7, "juli": 7,
    "aug": 8, "august": 8, "agu": 8, "agt": 8, "agustus": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "okt": 10, "oktober": 10, "nov": 11, "november": 11, "nop": 11, "nopember": 11,
    "dec": 12, "december": 12, "des": 12, "desember": 12,
}
_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_ORD = r"(?:st|nd|rd|th)?"
DATE_PATTERNS = [  # (regex, urutan grup)
    (re.compile(rf"\b(\d{{1,2}}){_ORD}[\s\-/.]*({_MONTH})\.?[\s\-/.,]*(\d{{4}})\b", re.I), "dmy"),   # 6 August 2026, 06-Aug-2026
    (re.compile(rf"\b({_MONTH})\.?[\s\-/.]*(\d{{1,2}}){_ORD}[\s,\-/.]+(\d{{4}})\b", re.I), "mdy"),  # August 06th 2026
    (re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"), "ymd"),                                 # 2026-08-06
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"), "dmy_num"),                              # 06/08/2026 (hari/bulan)
]
JOIN_KEYS = re.compile(
    r"(?:shall\s+join|will\s+join|will\s+be\s+joining|to\s+join|joining|join(?:ed)?(?:\s+date)?|"
    r"date\s+of\s+commencement|commencement(?:\s+date)?|commence|start(?:ing)?\s+(?:date|on)|effective|"
    r"\bDOC\b|tanggal\s+(?:masuk|bergabung|mulai)|bergabung|mulai\s+bekerja|masuk\s+kerja)", re.I)
# Cadangan: tanggal pada keterangan "Subject : New Recruitment on September 03rd 2026".
RECRUIT_KEYS = re.compile(r"new\s+recruitment|rekrut(?:men)?\s+baru|penerimaan\s+karyawan\s+baru", re.I)


def _to_date(kind, g):
    try:
        if kind == "dmy":
            return date(int(g[2]), MONTHS[g[1].casefold()], int(g[0]))
        if kind == "mdy":
            return date(int(g[2]), MONTHS[g[0].casefold()], int(g[1]))
        if kind == "ymd":
            return date(int(g[0]), int(g[1]), int(g[2]))
        return date(int(g[2]), int(g[1]), int(g[0]))
    except (ValueError, KeyError):
        return None


def parse_date(text: str):
    """Tanggal pertama pada teks (ISO) dari berbagai format Inggris/Indonesia; None bila tidak ada."""
    best = None
    for regex, kind in DATE_PATTERNS:
        for m in regex.finditer(text or ""):
            d = _to_date(kind, m.groups())
            if d and (best is None or m.start() < best[0]):
                best = (m.start(), d)
    return best[1].isoformat() if best else None


def extract_join_date(doc: Document):
    return extract_join_date_from_text(document_text(doc))


def extract_join_date_from_text(text: str):
    """Cari tanggal masuk (DOC) di dekat kata kunci seperti 'shall join', 'joining date', 'DOC', 'tanggal masuk'."""
    for keys in (JOIN_KEYS, RECRUIT_KEYS):  # frasa "join/DOC" didahulukan, lalu keterangan "New Recruitment"
        for key in keys.finditer(text or ""):
            found = parse_date(text[key.end(): key.end() + 70])
            if found:
                return found
    return None


# ----------------------------------------------------------------- validasi
def normalize_emp_no(value: str) -> str:
    value = clean(value)
    return value[:-2] if re.fullmatch(r"\d+\.0", value) else value  # "98420.0" -> "98420"


def split_department(value: str):
    """'2700 / Haemo' -> ('2700', 'Haemo'). Format salah -> ('', teks asli).

    Toleran terhadap variasi penulisan HR: pemisah / - – — : | atau spasi, dan urutan
    terbalik ('Haemo / 2700'). Hasilnya tetap divalidasi ketat oleh validate_record.
    """
    value = clean(value)
    match = DEPT_RE.match(value)
    if match:
        return match.group(1), match.group(2)
    match = DEPT_REVERSED_RE.match(value)
    if match:
        return match.group(2), match.group(1)
    return "", value


def validate_record(record: dict, seen_in_file: set | None = None):
    """Validasi satu record. Mengembalikan (record_bersih, daftar_alasan). Alasan kosong = valid.

    Dipakai dua kali: saat parsing file dan saat konfirmasi (data hasil edit pengguna
    tidak dipercaya begitu saja).
    """
    reasons = []
    rec = {
        "employee_number": normalize_emp_no(record.get("employee_number", "")),
        "employee_name": clean(record.get("employee_name", "")),
        "gender": clean(record.get("gender", "")),
        "department_code": clean(record.get("department_code", "")),
        "department_name": clean(record.get("department_name", "")),
        "shift": clean(record.get("shift", "")) or "Normal",
        "position": clean(record.get("position", "")),
        "status": clean(record.get("status", "")),
        "remarks": clean(record.get("remarks", "")),
        "doc": clean(record.get("doc", "")) or None,
        "source_row": record.get("source_row"),
    }
    if not rec["department_code"]:
        reasons.append("Format Sect/Dept tidak dikenali (contoh benar: 2700 / Haemo)")
    elif rec["department_code"] != TARGET_DEPT_CODE:
        reasons.append("Bukan section 2700 / Haemo")
    elif rec["department_name"].casefold() != TARGET_DEPT_NAME:
        reasons.append("Kode 2700 tetapi nama section bukan Haemo")

    missing = [label for key, label in (("employee_number", "Emp No"), ("employee_name", "Emp Name")) if not rec[key]]
    if missing:
        reasons.append("Field wajib kosong: " + ", ".join(missing))
    if rec["employee_number"] and not EMP_NO_RE.match(rec["employee_number"]):
        reasons.append("Format Emp No tidak valid (3-30 huruf/angka)")
    if rec["employee_name"] and not re.search(r"[A-Za-z]", rec["employee_name"]):
        reasons.append("Emp Name tidak valid")
    for key, limit in MAX_LEN.items():
        if len(rec[key]) > limit:
            reasons.append(f"{key} terlalu panjang (maks. {limit} karakter)")
    if rec["doc"]:
        try:
            date.fromisoformat(rec["doc"])
        except ValueError:
            reasons.append("Format DOC harus YYYY-MM-DD")
    if seen_in_file is not None and rec["employee_number"]:
        if rec["employee_number"] in seen_in_file:
            reasons.append("Emp No duplikat dalam file")
        elif not reasons:
            seen_in_file.add(rec["employee_number"])
    return rec, reasons


# ----------------------------------------------------------------- header
def _header_map(cells: list[str], ai_mapper, warnings: list[str]):
    """Petakan header sebuah baris. Aturan dulu; bila belum lengkap, minta bantuan AI."""
    mapping = [ALIASES.get(canonical(c), "") for c in cells]
    if REQUIRED_HEADERS <= set(mapping):
        return mapping, "aturan"
    if ai_mapper is None:
        return None, ""
    labels = [clean(c) for c in cells]
    # hanya baris yang tampak seperti header (ada teks, bukan data angka murni)
    if len({c for c in labels if c}) < 3 or any(re.fullmatch(r"\d{4,}", c) for c in labels):
        return None, ""
    ai_result = ai_mapper(labels) or {}
    merged = list(mapping)
    for index, field in ai_result.items():
        if isinstance(index, int) and 0 <= index < len(merged) and field in FIELDS and not merged[index] \
                and field not in merged:  # AI tidak boleh menimpa aturan atau memakai field dua kali
            merged[index] = field
    if REQUIRED_HEADERS <= set(merged):
        warnings.append("Sebagian header dikenali dengan bantuan AI; periksa kolom pada preview.")
        return merged, "AI"
    return None, ""


def build_result(raw_rows: list[dict], join_date, header_source: str, warnings: list[str]) -> dict:
    """Validasi baris mentah (dari Word maupun PDF) dan pisahkan per section.

    raw_rows: dict dengan kunci employee_number, employee_name, gender, department (teks Sect/Dept
    apa adanya), shift, position, status, remarks, source_row. Keputusan data hanya dibuat di sini
    oleh aturan deterministik, apa pun sumber dokumennya.
    """
    accepted, rejected, needs_review = [], [], []
    sections: dict[tuple, dict] = {}
    seen: set = set()

    for raw in raw_rows:
        code, name = split_department(raw.get("department", ""))
        label = f"{code} / {name}" if code else "Tidak dikenali"
        group = sections.setdefault((code, name.casefold() if code else ""), {
            "code": code, "name": name if code else "", "label": label,
            "is_target": code == TARGET_DEPT_CODE and name.casefold() == TARGET_DEPT_NAME, "employees": [],
        })
        group["employees"].append({
            "employee_number": clean(raw.get("employee_number", "")),
            "employee_name": clean(raw.get("employee_name", "")),
            "position": clean(raw.get("position", "")),
        })
        record = {
            "employee_number": raw.get("employee_number", ""),
            "employee_name": raw.get("employee_name", ""),
            "gender": raw.get("gender", ""),
            "department_code": code,
            "department_name": name,
            "shift": raw.get("shift", ""),
            "position": raw.get("position", ""),
            "status": raw.get("status", ""),
            "remarks": raw.get("remarks", ""),
            "doc": parse_date(raw.get("doc", "")) or join_date,
            "source_row": raw.get("source_row"),
        }
        if code and code != TARGET_DEPT_CODE:  # departemen lain: tidak diimpor
            rejected.append({
                "employee_number": clean(record["employee_number"]),
                "employee_name": clean(record["employee_name"]),
                "position": clean(record["position"]),
                "department": raw.get("department", ""),
                "reason": "Bukan section Haemo",
            })
            continue
        record, reasons = validate_record(record, seen)
        if reasons:
            needs_review.append({"record": record, "reason": "; ".join(reasons)})
        else:
            accepted.append(record)

    if not join_date and not any(parse_date(r.get("doc", "")) for r in raw_rows):
        warnings.append("Tanggal DOC tidak ditemukan di dokumen; isi pada preview bila diperlukan.")
    ordered = sorted(sections.values(), key=lambda g: (not g["is_target"], g["label"]))
    for g in ordered:
        g["count"] = len(g["employees"])
    total_rows = len(raw_rows)
    logger.info("Parsing selesai: total=%s haemo=%s lain=%s review=%s header=%s sections=%s",
                total_rows, len(accepted), len(rejected), len(needs_review), header_source, len(ordered))

    return {
        "summary": {
            "total_detected": total_rows,
            "haemo_candidates": len(accepted),
            "other_departments": len(rejected),
            "needs_review": len(needs_review),
            "join_date": join_date,
            "header_source": header_source,
        },
        "sections": ordered,
        "accepted": accepted,
        "rejected": rejected,
        "needs_review": needs_review,
        "warnings": warnings,
    }


def _iter_tables(container, seen=None):
    """Semua tabel pada dokumen, termasuk tabel di dalam sel (HR sering menempelkan email ke Word)."""
    seen = set() if seen is None else seen
    for table in container.tables:
        if id(table._tbl) in seen:
            continue
        seen.add(id(table._tbl))
        yield table
        for row in table.rows:
            for cell in row.cells:  # sel gabungan muncul berulang; `seen` mencegah pembacaan ganda
                yield from _iter_tables(cell, seen)


def _text_grids(doc) -> list[list[list[str]]]:
    """Tabel 'palsu': baris paragraf berpemisah tab atau | (hasil tempel dari email/Excel)."""
    grids, current = [], []
    for p in doc.paragraphs:
        text = p.text.strip()
        cells = [clean(c) for c in re.split(r"\t+|\s*\|\s*", text)] if ("\t" in text or "|" in text) else []
        if len([c for c in cells if c]) >= 3:
            current.append(cells)
        elif current:
            grids.append(current)
            current = []
    if current:
        grids.append(current)
    return grids


def document_text(doc, limit: int = 20000) -> str:
    """Seluruh isi dokumen sebagai teks (paragraf + baris tabel) untuk dibaca AI."""
    lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for table in _iter_tables(doc):
        for row in table.rows:
            cells = []
            for cell in row.cells:
                text = clean(cell.text)
                if text and (not cells or cells[-1] != text):
                    cells.append(text)
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)[:limit]


def parse_docx(file, ai_mapper="default", ai_extractor="default", ai_date="default") -> dict:
    """Baca dokumen recruitment otomatis. `file` boleh path atau file-like (UploadedFile).

    Urutan: (1) tabel Word (termasuk bersarang) -> (2) tabel teks berpemisah tab/| ->
    (3) AI membaca seluruh dokumen bila (1) dan (2) tidak menemukan header.
    ai_mapper: "default" = pakai AI bila ANTHROPIC_API_KEY ada; None = tanpa AI; atau fungsi(labels)
    -> {indeks: field}. ai_extractor: "default" mengikuti ai_mapper; None = tanpa AI; atau
    fungsi(teks) -> list baris mentah (dipakai untuk tes).
    """
    if ai_extractor == "default":
        ai_extractor = None if ai_mapper is None else extract_rows_with_ai
    if ai_date == "default":
        ai_date = None if ai_mapper is None else find_join_date_with_ai
    if ai_mapper == "default":
        ai_mapper = map_headers_with_ai
    doc = Document(file)
    join_date = extract_join_date(doc)
    warnings: list[str] = []
    raw_rows: list[dict] = []
    found_table = False
    header_source = "aturan"

    grids = [[[c.text for c in row.cells] for row in table.rows] for table in _iter_tables(doc)]
    grids += _text_grids(doc)
    for rows in grids:
        headers, start = None, 0
        for idx, cells in enumerate(rows[:HEADER_SCAN_ROWS]):
            headers, source = _header_map(cells, ai_mapper, warnings)
            if headers:
                start = idx + 1
                if source == "AI":
                    header_source = "AI"
                break
        if not headers:
            continue
        found_table = True

        for row_number, cells in enumerate(rows[start:], start=start + 1):
            values = [clean(c) for c in cells]
            if not any(values):
                continue
            raw = {name: values[i] for i, name in enumerate(headers) if name and i < len(values)}
            raw_rows.append({**raw, "source_row": row_number})

    if not found_table and ai_extractor is not None:
        text = document_text(doc)
        if text.strip():
            raw_rows = ai_extractor(text) or []
            if raw_rows:
                found_table, header_source = True, "AI"
                warnings.append("Struktur tabel tidak dikenali oleh aturan, sehingga isi dokumen dibaca otomatis oleh AI. "
                                "Periksa seluruh baris pada preview sebelum mengonfirmasi.")

    if not join_date and ai_date is not None and found_table:
        join_date = ai_date(document_text(doc))  # aturan gagal menemukan DOC -> AI membaca dokumen
        if join_date and not any(parse_date(r.get("doc", "")) for r in raw_rows):
            warnings.append("Tanggal DOC dibaca oleh AI; periksa pada preview.")

    if not found_table:
        hint = "" if ai_extractor is None or settings.ANTHROPIC_API_KEY else \
            " Untuk dokumen tanpa tabel, aktifkan pembacaan AI dengan mengatur ANTHROPIC_API_KEY."
        raise ValueError(
            "Tabel recruitment tidak ditemukan. Pastikan header berisi Emp. No, Employee Name, dan Sect/Dept." + hint
        )
    return build_result(raw_rows, join_date, header_source, warnings)
