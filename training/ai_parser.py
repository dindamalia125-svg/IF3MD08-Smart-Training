"""Modul parsing manpower (UC-07).

Teks dari HR dipisah menjadi Nama, Emp No., dan Kode Shift.
- Jika ANTHROPIC_API_KEY diatur, teks dikirim ke Claude (modul AI) dan hasilnya dipakai sebagai rekomendasi.
- Jika tidak, atau bila panggilan gagal, dipakai parser berbasis aturan (regex) sebagai fallback.
Hasil selalu berupa REKOMENDASI yang dapat diperbaiki Trainer sebelum disimpan.
"""
import json
import re
import urllib.error
import urllib.request

from django.conf import settings

EMP_NO_RE = re.compile(r"\b([A-Za-z]{1,4}-?\d{2,6})\b")
SPLIT_RE = re.compile(r"\s*(?:[-–—,;|\t]|\s{2,})\s*")
MAX_CHARS = 20000

def _rule_based(text, shift_codes):
    rows = []
    for raw in text.splitlines():
        line = raw.strip().strip("•*").strip()
        line = re.sub(r"^\d+[.)]\s+", "", line)  # buang penomoran "1. "
        if not line or line == "...":
            continue
        emp_no = nama = shift = ""
        m = EMP_NO_RE.search(line)
        if m:
            emp_no = m.group(1).upper()
        parts = [p.strip() for p in SPLIT_RE.split(line) if p.strip()]
        for p in parts:
            if p.upper() == emp_no:
                continue
            if p.upper() in shift_codes or p in shift_codes:
                shift = next((c for c in shift_codes if c.upper() == p.upper()), p)
            elif not nama and re.search(r"[A-Za-z]", p) and "?" not in p:
                nama = p
        rows.append({"nama": nama, "emp_no": emp_no, "shift": shift, "raw": raw.strip()})
    return rows


def _call_claude(text, shift_codes):
    prompt = (
        "Pisahkan daftar manpower berikut menjadi JSON array of object dengan kunci "
        '"nama", "emp_no", "shift". Kode shift yang valid: ' + ", ".join(shift_codes) + ". "
        'Jika suatu bagian tidak dapat dipastikan, isi dengan string kosong. Balas HANYA JSON.\n\n' + text
    )
    body = json.dumps({
        "model": settings.ANTHROPIC_MODEL, "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"content-type": "application/json", "x-api-key": settings.ANTHROPIC_API_KEY,
                 "anthropic-version": "2023-06-01"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    out = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    out = re.sub(r"^```(?:json)?|```$", "", out.strip(), flags=re.M).strip()
    items = json.loads(out)
    return [{"nama": str(i.get("nama", "")).strip(), "emp_no": str(i.get("emp_no", "")).strip().upper(),
             "shift": str(i.get("shift", "")).strip(), "raw": ""} for i in items]


def parse_manpower(text, shift_codes):
    """Kembalikan list baris {nama, emp_no, shift, raw, sumber}."""
    shift_codes = list(shift_codes)
    sumber = "aturan"
    rows = None
    if settings.ANTHROPIC_API_KEY:
        try:
            rows = _call_claude(text, shift_codes)
            sumber = "AI"
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
            rows = None
    if rows is None:
        rows = _rule_based(text, shift_codes)
    for r in rows:
        r["sumber"] = sumber
    return rows
