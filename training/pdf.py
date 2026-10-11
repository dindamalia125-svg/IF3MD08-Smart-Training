"""Pembuatan sertifikat PDF sesuai template standar (UC-10)."""
from io import BytesIO

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def build_certificates_pdf(certificates):
    """certificates: iterable Sertifikat -> bytes PDF (satu halaman per sertifikat)."""
    buf = BytesIO()
    w, h = landscape(A4)
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    count = 0
    for cert in certificates:
        count += 1
        c.setStrokeColorRGB(0.25, 0.25, 0.25)
        c.setLineWidth(2)
        c.rect(12 * mm, 12 * mm, w - 24 * mm, h - 24 * mm)
        c.setLineWidth(0.5)
        c.rect(16 * mm, 16 * mm, w - 32 * mm, h - 32 * mm)
        c.setFillColorRGB(0.87, 0.87, 0.87)
        c.circle(w / 2, h - 48 * mm, 14 * mm, stroke=1, fill=1)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(w / 2, h - 49.5 * mm, "LOGO")
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont("Helvetica-Bold", 30)
        c.drawCentredString(w / 2, h - 80 * mm, "SERTIFIKAT KUALIFIKASI")
        c.setFont("Helvetica", 13)
        c.drawCentredString(w / 2, h - 96 * mm, "Diberikan kepada")
        c.setFont("Helvetica-Bold", 26)
        c.drawCentredString(w / 2, h - 112 * mm, cert.trainee.nama)
        c.setFont("Helvetica", 13)
        c.drawCentredString(w / 2, h - 126 * mm, f"Nomor Badge {cert.trainee.badge}")
        c.drawCentredString(w / 2, h - 140 * mm,
                            f"dinyatakan QUALIFIED pada proses {cert.proses.nama}")
        c.drawCentredString(w / 2, h - 148 * mm, "dengan hasil evaluasi sesuai standar.")
        # tanda tangan & QR placeholder
        c.setStrokeColorRGB(0.2, 0.2, 0.2)
        c.line(40 * mm, 40 * mm, 100 * mm, 40 * mm)
        c.line(w - 100 * mm, 40 * mm, w - 40 * mm, 40 * mm)
        c.setFont("Helvetica", 10)
        c.drawCentredString(70 * mm, 34 * mm, "Trainer")
        c.drawCentredString(w - 70 * mm, 34 * mm, "Super Admin")
        c.rect(w / 2 - 10 * mm, 28 * mm, 20 * mm, 20 * mm)
        c.setFont("Helvetica", 8)
        c.drawCentredString(w / 2, 36 * mm, "QR")
        c.setFont("Helvetica", 9)
        c.drawCentredString(w / 2, 20 * mm, f"No. {cert.nomor} · {cert.tanggal:%d-%m-%Y}")
        c.showPage()
    if not count:
        raise ValueError("Tidak ada sertifikat untuk dibuat")
    c.save()
    return buf.getvalue()
