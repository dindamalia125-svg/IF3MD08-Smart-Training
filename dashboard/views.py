import calendar
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import super_admin_required, trainer_required
from training.models import Capaian, ProsesTrainee, Sertifikat, Trainee

BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
         "November", "Desember"]


def _periode(raw):
    today = timezone.localdate()
    try:
        y, m = (int(x) for x in raw.split("-"))
        date(y, m, 1)
    except (AttributeError, ValueError):
        y, m = today.year, today.month
    return y, m


@super_admin_required
def super_admin(request):
    """UC-06: ringkasan analitik pelatihan & penerbitan sertifikat."""
    y, m = _periode(request.GET.get("periode"))
    start, end = date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    caps = Capaian.objects.filter(aktif=True, tanggal__range=(start, end))

    harian = list(caps.values("tanggal").annotate(output=Sum("output"), reject=Sum("reject")).order_by("tanggal"))
    per_proses = list(caps.values("proses__nama").annotate(output=Sum("output")).order_by("-output"))
    has_data = Trainee.objects.exists() or Capaian.objects.exists()

    today = timezone.localdate()
    options = []
    yy, mm = today.year, today.month
    for _ in range(6):
        options.append({"value": f"{yy}-{mm:02d}", "label": f"{BULAN[mm - 1][:3]} {yy}"})
        mm -= 1
        if mm == 0:
            mm, yy = 12, yy - 1
    if not any(o["value"] == f"{y}-{m:02d}" for o in options):
        options.insert(0, {"value": f"{y}-{m:02d}", "label": f"{BULAN[m - 1][:3]} {y}"})

    ctx = {
        "has_data": has_data,
        "kpi": {
            "total": Trainee.objects.filter(aktif=True).count(),
            "training": Trainee.objects.filter(proses_list__status=ProsesTrainee.Status.TRAINING).distinct().count(),
            "qualified": Trainee.objects.filter(proses_list__status=ProsesTrainee.Status.QUALIFIED).distinct().count(),
            "sertifikat": Sertifikat.objects.count(),
        },
        "periode_label": f"{BULAN[m - 1]} {y}", "periode": f"{y}-{m:02d}", "periode_options": options,
        "chart_harian": {"labels": [h["tanggal"].strftime("%d/%m") for h in harian],
                         "output": [h["output"] for h in harian], "reject": [h["reject"] for h in harian]},
        "chart_proses": {"labels": [p["proses__nama"] for p in per_proses], "output": [p["output"] for p in per_proses]},
        "ada_capaian_periode": bool(harian),
        "sertifikat_terbaru": Sertifikat.objects.select_related("trainee", "proses", "dicetak_oleh")[:5],
    }
    return render(request, "dashboard/super_admin.html", ctx)


@trainer_required
def trainer(request):
    """UC-12 (masa training) dan UC-13 (finish kontrak)."""
    today = timezone.localdate()
    warnings = []
    for pt in ProsesTrainee.objects.filter(status=ProsesTrainee.Status.TRAINING).select_related("trainee", "proses"):
        maks = pt.proses.durasi_maks_hari
        if not maks:  # durasi belum diatur -> tidak ada peringatan
            continue
        ratio = pt.lama_hari / maks
        if ratio >= settings.TRAINING_WARNING_RATIO:
            warnings.append({"pt": pt, "maks": maks, "persen": round(ratio * 100), "lewat": ratio >= 1})
    warnings.sort(key=lambda w: -w["persen"])

    contracts = []
    batas = today + timedelta(days=settings.CONTRACT_WARNING_DAYS)
    qs = Trainee.objects.filter(aktif=True, kontrak_berakhir__range=(today, batas)).select_related("lini", "shift") \
        .order_by("kontrak_berakhir")
    for t in qs:
        pt = t.proses_list.select_related("proses").first()
        parts = [t.lini.lokasi_lengkap if t.lini else "-"]
        if pt:
            parts.append(pt.proses.nama)
        contracts.append({"t": t, "lokasi": " · ".join(parts), "sisa": (t.kontrak_berakhir - today).days})

    ctx = {
        "warnings": warnings, "contracts": contracts, "bell": len(warnings) + len(contracts),
        "kpi": {
            "training": Trainee.objects.filter(proses_list__status=ProsesTrainee.Status.TRAINING).distinct().count(),
            "dekat_batas": len(warnings), "kontrak": len(contracts), "sertifikat": Sertifikat.objects.count(),
        },
        "hari_kontrak": settings.CONTRACT_WARNING_DAYS,
    }
    return render(request, "dashboard/trainer.html", ctx)
