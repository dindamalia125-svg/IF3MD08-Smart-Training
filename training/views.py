import re
from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.audit import log
from accounts.decorators import trainer_required
from master.models import Proses, Shift

from .ai_parser import parse_manpower
from .evaluasi import evaluasi_trainee
from .forms import CapaianForm
from .models import Capaian, ProsesTrainee, RiwayatShift, Sertifikat, Trainee
from .pdf import build_certificates_pdf
from io import BytesIO


# ---------------------------------------------------------------- UC-07
def _annotate(rows, shift_codes):
    """Tandai tiap baris: ok / gagal (AI tidak bisa memisah) / duplikat (badge sudah ada)."""
    existing = set(Trainee.objects.values_list("badge", flat=True))
    seen = set()
    valid_shift = {c.upper(): c for c in shift_codes}
    out = []
    for r in rows:
        nama, badge, shift = r["nama"].strip(), r["badge"].strip().upper(), r["shift"].strip()
        shift = valid_shift.get(shift.upper(), shift)
        row = {"nama": nama, "badge": badge, "shift": shift}
        if not (nama and badge and shift in valid_shift.values()):
            row.update(status="gagal", pesan="AI gagal memisahkan baris, perbaiki manual")
        elif badge in existing or badge in seen:
            row.update(status="duplikat", pesan="Nomor Badge sudah ada (duplikat), baris ditolak")
        else:
            row.update(status="ok", pesan="OK")
            seen.add(badge)
        out.append(row)
    return out


@trainer_required
def manpower(request):
    shift_codes = list(Shift.objects.values_list("kode", flat=True))
    ctx = {"teks": "", "shift_codes": shift_codes, "rows": None}
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "proses":
            teks = request.POST.get("teks", "").strip()
            ctx["teks"] = teks
            if not teks:
                ctx["error"] = "Teks kosong: tempelkan data manpower terlebih dahulu"
            else:
                ctx["rows"] = _annotate(parse_manpower(teks, shift_codes), shift_codes)
        elif action == "simpan":
            names = request.POST.getlist("nama")
            badges = request.POST.getlist("badge")
            shifts = request.POST.getlist("shift")
            rows = _annotate([{"nama": n, "badge": b, "shift": s} for n, b, s in zip(names, badges, shifts)], shift_codes)
            saved = 0
            with transaction.atomic():
                for row in rows:
                    if row["status"] != "ok":
                        continue
                    shift = Shift.objects.get(kode=row["shift"])
                    t = Trainee.objects.create(badge=row["badge"], nama=row["nama"], shift=shift,
                                               mulai_training=timezone.localdate())
                    RiwayatShift.objects.create(trainee=t, shift=shift, mulai=timezone.localdate())
                    row["status"], row["pesan"] = "tersimpan", "Tersimpan"
                    saved += 1
            rejected = len(rows) - saved
            log(request.user, "Parsing manpower", "Data manpower",
                f"{saved} baris disimpan, {rejected} baris ditolak (gagal parsing atau duplikat badge)")
            ctx["rows"] = rows
            ctx["saved"], ctx["rejected"] = saved, rejected
            ctx["teks"] = request.POST.get("teks", "")
    return render(request, "training/manpower.html", ctx)


# ---------------------------------------------------------------- UC-08
@trainer_required
def capaian(request):
    form = CapaianForm(request.POST or None)
    ctx = {"form": form, "proses_all": Proses.objects.all()}
    sel_trainee = sel_proses = None
    if request.method == "POST":
        if form.is_valid():
            d = form.cleaned_data
            existing = Capaian.objects.filter(trainee=d["trainee"], proses=d["proses"], tanggal=d["tanggal"], aktif=True).first()
            if existing and not request.POST.get("timpa"):
                ctx["konfirmasi_timpa"] = True
                sel_trainee, sel_proses = d["trainee"], d["proses"]
            else:
                with transaction.atomic():
                    if existing:
                        existing.aktif = False
                        existing.save(update_fields=["aktif"])
                    Capaian.objects.create(trainee=d["trainee"], proses=d["proses"], tanggal=d["tanggal"],
                                           output=d["output"], reject=d["reject"], dicatat_oleh=request.user)
                    ProsesTrainee.objects.get_or_create(trainee=d["trainee"], proses=d["proses"],
                                                        defaults={"mulai": d["tanggal"]})
                log(request.user, "Input data", "Capaian harian",
                    f"{d['trainee'].badge} · {d['proses'].nama} · output {d['output']}, reject {d['reject']}")
                messages.success(request, "Capaian tersimpan, riwayat sebelumnya tidak dihapus")
                return redirect(f"{reverse('training:capaian')}?trainee={d['trainee'].pk}&proses={d['proses'].pk}")
        else:
            ctx["error"] = form.first_error()
            sel_trainee = form.fields["trainee"].queryset.filter(pk=request.POST.get("trainee") or 0).first()
            sel_proses = Proses.objects.filter(pk=request.POST.get("proses") or 0).first()
    else:
        sel_trainee = Trainee.objects.filter(pk=request.GET.get("trainee") or 0).first()
        sel_proses = Proses.objects.filter(pk=request.GET.get("proses") or 0).first()
        form = CapaianForm(initial={"trainee": sel_trainee, "proses": sel_proses, "tanggal": timezone.localdate()})
        ctx["form"] = form

    ctx["sel_proses"] = sel_proses
    ctx["sel_trainee"] = sel_trainee
    if sel_trainee:
        qs = Capaian.objects.filter(trainee=sel_trainee, aktif=True).select_related("proses", "dicatat_oleh")
        ctx["riwayat"] = qs[:5]
        latest = qs.filter(proses=sel_proses).first() if sel_proses else qs.first()
        ctx["progress"] = latest.persen_target if latest else None
        ctx["progress_cap"] = min(ctx["progress"], 100) if latest else 0
    return render(request, "training/capaian.html", ctx)


# ---------------------------------------------------------------- UC-09
@trainer_required
def penelusuran(request):
    q = request.GET.get("q", "").strip()
    ctx = {"q": q}
    if q:
        qs = Trainee.objects.filter(Q(badge__icontains=q) | Q(nama__icontains=q)).select_related("shift", "lini")
        exact = list(qs.filter(badge__iexact=q))
        results = exact if len(exact) == 1 else list(qs[:50])
        if not results:
            ctx["tidak_ditemukan"] = True
        elif len(results) == 1:
            return redirect(f"{reverse('training:trainee_profil', args=[results[0].pk])}?q={q}")
        else:
            ctx["results"] = results
    return render(request, "training/penelusuran.html", ctx)


@trainer_required
def trainee_profil(request, pk):
    t = get_object_or_404(Trainee.objects.select_related("shift", "lini"), pk=pk)
    return render(request, "training/profil.html", {
        "t": t, "q": request.GET.get("q", t.badge),
        "riwayat_shift": t.riwayat_shift.select_related("shift", "lini"),
        "proses_list": t.proses_list.select_related("proses"),
    })


# ---------------------------------------------------------------- UC-10
@trainer_required
def sertifikat(request):
    return render(request, "training/sertifikat_index.html", {
        "trainees": Trainee.objects.filter(aktif=True).select_related("shift")[:100],
        "recent": Sertifikat.objects.select_related("trainee", "proses", "dicetak_oleh")[:10],
    })


def _cert_ids(raw):
    return [int(x) for x in re.findall(r"\d+", raw or "")]


@trainer_required
def evaluasi(request, pk):
    t = get_object_or_404(Trainee.objects.select_related("shift", "lini"), pk=pk)
    rows = evaluasi_trainee(t)
    ctx = {"t": t, "rows": rows}

    if request.method == "POST" and request.POST.get("action") == "cetak":
        decisions = {r["pt"].pk: request.POST.get(f"verifikasi_{r['pt'].pk}", "tidak") for r in rows}
        for r in rows:
            r["verifikasi"] = decisions[r["pt"].pk]
        eligible = [r for r in rows if r["rekomendasi"] and r["verifikasi"] == "setuju"]
        if not eligible:
            ctx["error_tidak_layak"] = True
        else:
            try:
                with transaction.atomic():
                    certs = []
                    for r in eligible:
                        c = Sertifikat.objects.create(
                            nomor=Sertifikat.nomor_berikutnya(), trainee=t, proses=r["proses"],
                            dicetak_oleh=request.user, rata_output=r["rata"])
                        certs.append(c)
                        pt = r["pt"]
                        pt.status = ProsesTrainee.Status.QUALIFIED
                        pt.tanggal_qualified = pt.tanggal_qualified or timezone.localdate()
                        pt.save(update_fields=["status", "tanggal_qualified"])
                    build_certificates_pdf(certs)  # validasi: PDF harus berhasil dibuat sebelum commit
            except Exception:  # noqa: BLE001 - kegagalan apa pun pada pembuatan PDF
                ctx["error_pdf"] = True
            else:
                for c in certs:
                    log(request.user, "Cetak sertifikat", "Sertifikat", f"{c.nomor} · {t.nama}")
                messages.success(request, "Sertifikat berhasil dibuat dan aktivitas pencetakan dicatat di audit log")
                ids = ",".join(str(c.pk) for c in certs)
                return redirect(f"{reverse('training:evaluasi', args=[t.pk])}?cert={ids}")
        rows = evaluasi_trainee(t)
        for r in rows:
            r["verifikasi"] = decisions.get(r["pt"].pk, "tidak")
        ctx["rows"] = rows
    else:
        for r in rows:
            r["verifikasi"] = "setuju" if r["rekomendasi"] else "tidak"

    ctx["cert_ids"] = ",".join(str(i) for i in _cert_ids(request.GET.get("cert")))
    ctx["preview"] = next((r for r in ctx["rows"] if r["rekomendasi"] and r["verifikasi"] == "setuju"), None)
    ctx["bisa_cetak"] = ctx["preview"] is not None
    ctx["tidak_layak"] = any(not r["rekomendasi"] or r["verifikasi"] != "setuju" for r in ctx["rows"]) and not ctx["bisa_cetak"]
    return render(request, "training/evaluasi.html", ctx)


@trainer_required
def sertifikat_pdf(request):
    ids = _cert_ids(request.GET.get("ids"))
    certs = list(Sertifikat.objects.filter(pk__in=ids).select_related("trainee", "proses"))
    if not certs:
        raise Http404("Sertifikat tidak ditemukan")
    data = build_certificates_pdf(certs)
    name = f"{certs[0].nomor}.pdf" if len(certs) == 1 else f"sertifikat_{certs[0].trainee.badge}.pdf"
    return FileResponse(BytesIO(data), content_type="application/pdf", as_attachment=bool(request.GET.get("unduh")),
                        filename=name)
