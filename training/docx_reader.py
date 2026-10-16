"""Ekstraksi teks dari dokumen Word (.docx) untuk parsing manpower (UC-07).

Dokumen dari HR dapat berisi paragraf biasa (satu karyawan per baris), daftar bernomor,
maupun tabel. Semuanya diubah menjadi teks satu-baris-per-karyawan, lalu diteruskan ke
`ai_parser.parse_manpower` (Claude, atau parser aturan sebagai fallback).
"""
import re
import zipfile
from io import BytesIO

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

MAX_BYTES = 5 * 1024 * 1024  # batas ukuran unggahan: 5 MB
MAX_CHARS = 20000  # batas teks yang dikirim ke parser/AI

# Baris judul kolom tabel (mis. "No | Nama | Nomor Badge | Shift") tidak boleh dianggap karyawan.
HEADER_WORDS = {"no", "nomor", "nama", "name", "badge", "no badge", "nomor badge", "id", "nik", "shift",
                "kode shift", "nama karyawan", "nama lengkap", "npk"}


class DocxError(ValueError):
    """Berkas tidak dapat dibaca sebagai dokumen Word."""


def _is_header_row(cells):
    words = [c.strip().lower() for c in cells if c.strip()]
    return bool(words) and all(w in HEADER_WORDS for w in words)


def _iter_blocks(doc):
    """Paragraf dan tabel sesuai urutan kemunculan di dokumen."""
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            yield Paragraph(child, doc)
        elif tag == "tbl":
            yield Table(child, doc)


def _table_lines(table):
    lines = []
    for row in table.rows:
        cells, last = [], None
        for cell in row.cells:
            if cell._tc is last:  # sel yang digabung (merge) muncul berulang
                continue
            last = cell._tc
            text = re.sub(r"\s+", " ", cell.text).strip()
            if text:
                cells.append(text)
        if cells and not _is_header_row(cells):
            lines.append(" | ".join(cells))
    return lines


def extract_text(fileobj):
    """Kembalikan teks (satu baris per karyawan) dari file-like .docx. Raise DocxError bila gagal."""
    data = fileobj.read()
    if len(data) > MAX_BYTES:
        raise DocxError("Ukuran file terlalu besar (maksimal 5 MB)")
    try:
        doc = Document(BytesIO(data))
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as exc:
        raise DocxError("File tidak dapat dibaca. Pastikan formatnya .docx yang valid") from exc

    lines = []
    for block in _iter_blocks(doc):
        if isinstance(block, Paragraph):
            for part in block.text.splitlines():  # baris baru lunak (Shift+Enter)
                part = part.strip()
                if part:
                    lines.append(part)
        else:
            lines.extend(_table_lines(block))
    text = "\n".join(lines)
    if not text:
        raise DocxError("Dokumen kosong: tidak ada teks yang dapat dibaca")
    return text[:MAX_CHARS]
