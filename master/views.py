from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.audit import log
from accounts.decorators import super_admin_required

from .forms import LiniForm, ProsesForm, ShiftForm
from .models import Lini, Proses, Shift


def _diff(instance_before, form, labels):
    """Ringkas perubahan field, contoh: 'target harian 180 → 200'."""
    parts = []
    for field, label in labels.items():
        old, new = instance_before.get(field), form.cleaned_data.get(field)
        if old != new:
            parts.append(f"{label} {old} → {new}")
    return ", ".join(parts)


# ---------------------------------------------------------------- UC-03
@super_admin_required
def proses_list(request, pk=None):
    instance = get_object_or_404(Proses, pk=pk) if pk else None
    show_form = show_form = pk is not None or request.resolver_match.url_name == "proses_add" or request.method == "POST"
    form = None
    if request.method == "POST":
        before = {f: getattr(instance, f) for f in ("nama", "target_harian", "durasi_maks_hari")} if instance else {}
        form = ProsesForm(request.POST, instance=instance)
        if form.is_valid():
            creating = instance is None
            obj = form.save()
            if creating:
                log(request.user, "Tambah data", "Master proses", f"{obj.kode} {obj.nama} ditambahkan")
            else:
                detail = _diff(before, form, {"nama": "nama", "target_harian": "target harian",
                                              "durasi_maks_hari": "durasi maks."})
                log(request.user, "Ubah data", "Master proses", f"{obj.kode} {detail or 'diperbarui'}")
            messages.success(request, "Data proses berhasil disimpan")
            return redirect("master:proses_list")
    elif show_form:
        form = ProsesForm(instance=instance)
    page = Paginator(Proses.objects.all(), 5).get_page(request.GET.get("page"))
    return render(request, "master/proses_list.html", {"page": page, "form": form, "editing": instance})


@super_admin_required
@require_POST
def proses_delete(request, pk):
    obj = get_object_or_404(Proses, pk=pk)
    try:
        obj.delete()
    except ProtectedError:
        messages.error(request, f"Proses {obj.kode} tidak dapat dihapus karena sudah dipakai pada data capaian.")
    else:
        log(request.user, "Ubah data", "Master proses", f"{obj.kode} dihapus")
        messages.success(request, f"Proses {obj.kode} dihapus")
    return redirect("master:proses_list")


# ---------------------------------------------------------------- UC-04
@super_admin_required
def shift_lini(request):
    shift_inst = get_object_or_404(Shift, pk=request.GET["ubah_shift"]) if request.GET.get("ubah_shift") else None
    lini_inst = get_object_or_404(Lini, pk=request.GET["ubah_lini"]) if request.GET.get("ubah_lini") else None
    shift_form = ShiftForm(instance=shift_inst, prefix="shift")
    lini_form = LiniForm(instance=lini_inst, prefix="lini")

    if request.method == "POST":
        kind = request.POST.get("form_type")
        if kind == "shift":
            inst = get_object_or_404(Shift, pk=request.POST["pk"]) if request.POST.get("pk") else None
            shift_form = ShiftForm(request.POST, instance=inst, prefix="shift")
            shift_inst = inst
            if shift_form.is_valid():
                obj = shift_form.save()
                log(request.user, "Ubah data" if inst else "Tambah data", "Master shift", f"{obj.kode} {obj.nama}")
                messages.success(request, "Data berhasil disimpan (timestamp dan ID pelaksana tercatat di audit log)")
                return redirect("master:shift_lini")
        elif kind == "lini":
            inst = get_object_or_404(Lini, pk=request.POST["pk"]) if request.POST.get("pk") else None
            lini_form = LiniForm(request.POST, instance=inst, prefix="lini")
            lini_inst = inst
            if lini_form.is_valid():
                obj = lini_form.save()
                log(request.user, "Ubah data" if inst else "Tambah data", "Master lini", f"{obj.nama} · {obj.lokasi}")
                messages.success(request, "Data berhasil disimpan (timestamp dan ID pelaksana tercatat di audit log)")
                return redirect("master:shift_lini")

    return render(request, "master/shift_lini.html", {
        "shifts": Shift.objects.all(), "linis": Lini.objects.all(),
        "shift_form": shift_form, "lini_form": lini_form, "shift_inst": shift_inst, "lini_inst": lini_inst,
    })


def _delete_simple(request, model, pk, objek, label):
    obj = get_object_or_404(model, pk=pk)
    text = label(obj)
    try:
        obj.delete()
    except ProtectedError:
        messages.error(request, f"{text} tidak dapat dihapus karena masih dipakai data lain.")
    else:
        log(request.user, "Ubah data", objek, f"{text} dihapus")
        messages.success(request, f"{text} dihapus")
    return redirect("master:shift_lini")


@super_admin_required
@require_POST
def shift_delete(request, pk):
    return _delete_simple(request, Shift, pk, "Master shift", lambda o: f"Shift {o.kode}")


@super_admin_required
@require_POST
def lini_delete(request, pk):
    return _delete_simple(request, Lini, pk, "Master lini", lambda o: f"Lini {o.nama}")
