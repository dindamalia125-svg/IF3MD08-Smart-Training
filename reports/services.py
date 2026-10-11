"""Penyusunan rekapitulasi training harian/bulanan (UC-11)."""
import calendar
from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from training.models import Capaian

HEADERS = ["Badge", "Nama", "Proses", "Output", "Reject", "% Target"]


def parse_periode(jenis, raw):
    """Kembalikan (start, end, label_file) atau None bila periode tidak valid/kosong."""
    try:
        if jenis == "bulanan":
            y, m = (int(x) for x in raw.split("-"))
            return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1]), f"{y}-{m:02d}"
        d = datetime.strptime(raw, "%Y-%m-%d").date()
        return d, d, d.isoformat()
    except (AttributeError, ValueError):
        return None


def rekap_rows(start, end):
    agg = {}
    caps = Capaian.objects.filter(aktif=True, tanggal__range=(start, end)).select_related("trainee", "proses")
    for c in caps:
        k = (c.trainee_id, c.proses_id)
        a = agg.setdefault(k, {"badge": c.trainee.badge, "nama": c.trainee.nama, "proses": c.proses.nama,
                               "target": c.proses.target_harian, "output": 0, "reject": 0, "hari": 0})
        a["output"] += c.output
        a["reject"] += c.reject
        a["hari"] += 1
    rows = []
    for a in sorted(agg.values(), key=lambda r: (r["badge"], r["proses"])):
        denom = a["target"] * a["hari"]
        a["persen"] = round(a["output"] / denom * 100) if denom else 0
        rows.append(a)
    return rows


def build_xlsx(rows, judul):
    wb = Workbook()
    ws = wb.active
    ws.title = "Rekap Training"
    ws.append([judul])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    ws.append(HEADERS)
    for cell in ws[3]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F6FD0")
        cell.alignment = Alignment(horizontal="center")
    for r in rows:
        ws.append([r["badge"], r["nama"], r["proses"], r["output"], r["reject"], r["persen"] / 100])
    for row in ws.iter_rows(min_row=4, min_col=6, max_col=6):
        row[0].number_format = "0%"
    for col, width in zip("ABCDEF", (12, 28, 20, 10, 10, 10)):
        ws.column_dimensions[col].width = width
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_pdf(rows, judul):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=judul, leftMargin=30, rightMargin=30)
    styles = getSampleStyleSheet()
    data = [HEADERS] + [[r["badge"], r["nama"], r["proses"], r["output"], r["reject"], f"{r['persen']}%"] for r in rows]
    table = Table(data, repeatRows=1, colWidths=[80, 200, 140, 70, 70, 70])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F6FD0")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FA")]),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
    ]))
    doc.build([Paragraph(judul, styles["Title"]), Spacer(1, 10), table])
    return buf.getvalue()
