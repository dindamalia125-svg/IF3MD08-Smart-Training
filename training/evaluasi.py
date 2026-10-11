"""Rekomendasi kualifikasi (UC-10): rata-rata output dibandingkan dengan target proses."""
from django.conf import settings
from django.db.models import Avg, Count

from .models import Capaian, ProsesTrainee


def evaluasi_trainee(trainee):
    rows = []
    for pt in trainee.proses_list.select_related("proses"):
        agg = Capaian.objects.filter(trainee=trainee, proses=pt.proses, aktif=True).aggregate(
            rata=Avg("output"), hari=Count("id"))
        rata = round(agg["rata"] or 0)
        target = pt.proses.target_harian
        qualified = bool(agg["hari"]) and rata >= target * settings.QUALIFY_THRESHOLD
        rows.append({
            "pt": pt, "proses": pt.proses, "target": target, "rata": rata, "hari": agg["hari"],
            "rekomendasi": qualified, "sudah_qualified": pt.status == ProsesTrainee.Status.QUALIFIED,
        })
    return rows
