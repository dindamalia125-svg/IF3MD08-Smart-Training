from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from docx import Document

TARGET_DEPT_CODE = "2700"
ALIASES = {
    "empno": "employee_number",
    "employeeno": "employee_number",
    "employeenumber": "employee_number",
    "nik": "employee_number",
    "employeename": "employee_name",
    "nama": "employee_name",
    "namakaryawan": "employee_name",
    "gender": "gender",
    "sectdept": "department",
    "sectiondepartment": "department",
    "shift": "shift",
    "position": "position",
    "employmentstatus": "status",
    "status": "status",
    "replacement": "remarks",
}


def canonical(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def extract_join_date(doc: Document):
    text = "\n".join(p.text for p in doc.paragraphs)
    patterns = [
        r"\b(?:shall\s+join|join\s+date|date\s+of\s+commencement|commencement\s+date)\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?\s+\d{4})",
        r"\b(?:shall\s+join|join\s+date|date\s+of\s+commencement|commencement\s+date)\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        raw = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", match.group(1), flags=re.I)
        for fmt in ("%B %d %Y", "%d %B %Y"):
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                pass
    return None


def parse_docx(filepath: str | Path) -> dict:
    doc = Document(filepath)
    join_date = extract_join_date(doc)
    accepted, rejected, needs_review = [], [], []
    seen = set()
    total_rows = 0
    found_table = False

    for table in doc.tables:
        if not table.rows:
            continue
        headers = [ALIASES.get(canonical(cell.text), "") for cell in table.rows[0].cells]
        if not {"employee_number", "employee_name", "department"}.issubset(set(headers)):
            continue
        found_table = True

        for row_number, row in enumerate(table.rows[1:], start=2):
            values = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            if not any(values):
                continue
            total_rows += 1
            raw = {name: values[i] for i, name in enumerate(headers) if name and i < len(values)}
            dept_value = re.sub(r"\s+", " ", raw.get("department", "")).strip()
            match = re.match(r"^\s*(\d+)\s*/\s*(.+?)\s*$", dept_value)
            dept_code, dept_name = (match.group(1), match.group(2)) if match else ("", dept_value)

            record = {
                "employee_number": raw.get("employee_number", "").strip(),
                "employee_name": raw.get("employee_name", "").strip(),
                "gender": raw.get("gender", "").strip(),
                "department_code": dept_code,
                "department_name": dept_name,
                "shift": raw.get("shift", "").strip() or "Normal",
                "position": raw.get("position", "").strip(),
                "status": raw.get("status", "").strip(),
                "remarks": raw.get("remarks", "").strip(),
                "doc": join_date,
                "source_row": row_number,
            }

            if not dept_code:
                needs_review.append({"record": record, "reason": "Format Sect/Dept tidak dikenali"})
                continue
            if dept_code != TARGET_DEPT_CODE:
                rejected.append({
                    "employee_number": record["employee_number"],
                    "department": dept_value,
                    "reason": "Bukan section Haemo",
                })
                continue

            missing = [
                field for field in ("employee_number", "employee_name")
                if not record.get(field)
            ]
            if missing:
                needs_review.append({
                    "record": record,
                    "reason": "Field wajib kosong: " + ", ".join(missing),
                })
                continue
            if record["employee_number"] in seen:
                needs_review.append({"record": record, "reason": "Emp No duplikat dalam file"})
                continue
            seen.add(record["employee_number"])
            accepted.append(record)

    if not found_table:
        raise ValueError(
            "Tabel recruitment tidak ditemukan. Pastikan header berisi Emp. No, Employee Name, dan Sect/Dept."
        )

    return {
        "summary": {
            "total_detected": total_rows,
            "haemo_candidates": len(accepted),
            "other_departments": len(rejected),
            "needs_review": len(needs_review),
            "join_date": join_date,
        },
        "accepted": accepted,
        "rejected": rejected,
        "needs_review": needs_review,
    }
