"""Ekstrak teks dari berkas .docx / .pdf untuk parsing manpower (UC-07)."""
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from .ai_parser import EMP_NO_RE, MAX_CHARS

MAX_BYTES = 5 * 1024 * 1024


class BerkasError(Exception):
    pass


def _from_docx(upload):
    try:
        doc = Document(upload)
    except Exception as exc:
        raise BerkasError("Berkas .docx rusak atau tidak dapat dibaca") from exc
    lines = []
    for table in doc.tables:
        for i, row in enumerate(table.rows):
            cells = []
            for c in row.cells:
                t = c.text.strip().replace("\n", " ")
                if t and (not cells or cells[-1] != t):  # sel gabungan terbaca ganda
                    cells.append(t)
            line = " - ".join(cells)
            if not line or (i == 0 and not EMP_NO_RE.search(line)):  # lewati baris judul
                continue
            lines.append(line)
    if not lines:
        lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return lines


def _from_pdf(upload):
    try:
        reader = PdfReader(upload)
        if reader.is_encrypted:
            raise BerkasError("PDF dilindungi kata sandi")
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except BerkasError:
        raise
    except Exception as exc:
        raise BerkasError("Berkas PDF rusak atau tidak dapat dibaca") from exc
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise BerkasError("PDF tidak berisi teks (kemungkinan hasil scan/gambar)")
    return lines


def extract_text(upload):
    ext = Path(upload.name).suffix.lower()
    if ext not in (".docx", ".pdf"):
        raise BerkasError("Berkas harus berformat .docx atau .pdf")
    if upload.size > MAX_BYTES:
        raise BerkasError("Ukuran berkas maksimal 5 MB")
    lines = _from_docx(upload) if ext == ".docx" else _from_pdf(upload)
    if not lines:
        raise BerkasError("Berkas kosong")
    return "\n".join(lines)[:MAX_CHARS]