from urllib.parse import urlencode

from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.audit import log
from accounts.decorators import trainer_required

from .services import build_pdf, build_xlsx, parse_periode, rekap_rows

CONTENT_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}
ERR = "Periode belum dipilih / tidak ada data pada periode ini"


def _params(source):
    jenis = source.get("jenis") if source.get("jenis") in ("harian", "bulanan") else "harian"
    fmt = source.get("format") if source.get("format") in CONTENT_TYPES else "xlsx"
    raw = source.get("periode_bulanan" if jenis == "bulanan" else "periode_harian", "")
    return jenis, fmt, raw


def _filename(jenis, label, fmt):
    return f"rekap_training_{label}.{fmt}" if jenis == "harian" else f"rekap_training_bulanan_{label}.{fmt}"


@trainer_required
def ekspor(request):
    source = request.POST if request.method == "POST" else request.GET
    jenis, fmt, raw = _params(source)
    today = timezone.localdate()
    if not raw and request.method != "POST":
        raw = today.isoformat() if jenis == "harian" else today.strftime("%Y-%m")
    per = parse_periode(jenis, raw)
    rows = rekap_rows(per[0], per[1]) if per else []
    ctx = {"jenis": jenis, "format": fmt, "periode_harian": raw if jenis == "harian" else today.isoformat(),
           "periode_bulanan": raw if jenis == "bulanan" else today.strftime("%Y-%m"), "rows": rows}

    if request.method == "POST":
        if not per or not rows:
            ctx["error"] = ERR
        else:
            qs = urlencode({"jenis": jenis, "format": fmt,
                            "periode_bulanan" if jenis == "bulanan" else "periode_harian": raw, "siap": 1})
            return redirect(f"{reverse('reports:ekspor')}?{qs}")
    elif request.GET.get("siap") and per and rows:
        ctx["siap"] = True
        ctx["filename"] = _filename(jenis, per[2], fmt)
        ctx["unduh_qs"] = urlencode({"jenis": jenis, "format": fmt,
                                     "periode_bulanan" if jenis == "bulanan" else "periode_harian": raw})
    return render(request, "reports/ekspor.html", ctx)


@trainer_required
def unduh(request):
    jenis, fmt, raw = _params(request.GET)
    per = parse_periode(jenis, raw)
    rows = rekap_rows(per[0], per[1]) if per else []
    if not per or not rows:
        return redirect("reports:ekspor")
    judul = f"Rekapitulasi Training {'Harian' if jenis == 'harian' else 'Bulanan'} — {per[2]}"
    data = build_xlsx(rows, judul) if fmt == "xlsx" else build_pdf(rows, judul)
    name = _filename(jenis, per[2], fmt)
    resp = HttpResponse(data, content_type=CONTENT_TYPES[fmt])
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    log(request.user, "Ekspor laporan", "Laporan", f"{name} ({len(rows)} baris)")
    return resp
