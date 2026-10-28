import json
import logging
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.audit import log
from accounts.decorators import trainer_required
from master.models import Shift
from training.models import RiwayatShift, Trainee

from .forms import DocumentUploadForm
from .models import Manpower
from .word_parser import TARGET_DEPT_CODE, parse_docx

logger = logging.getLogger(__name__)


def _create_trainee(row, doc_date):
    """Buat Trainee + RiwayatShift dari baris impor. Return True bila dibuat."""
    emp_no = row["employee_number"].strip().upper()
    if Trainee.objects.filter(emp_no__iexact=emp_no).exists():
        return False
    shift = Shift.objects.filter(kode__iexact=(row.get("shift") or "").strip()).first()
    mulai = doc_date or timezone.localdate()
    t = Trainee.objects.create(emp_no=emp_no, nama=row["employee_name"], shift=shift, mulai_training=mulai)
    if shift:
        RiwayatShift.objects.create(trainee=t, shift=shift, mulai=mulai)
    return True


def _sync_trainee_shift(emp_no, kode):
    t = Trainee.objects.filter(emp_no__iexact=emp_no).first()
    shift = Shift.objects.filter(kode__iexact=kode).first()
    if not t or not shift or t.shift_id == shift.pk:
        return
    today = timezone.localdate()
    with transaction.atomic():
        t.riwayat_shift.filter(selesai__isnull=True).update(selesai=today)
        RiwayatShift.objects.create(trainee=t, shift=shift, lini=t.lini, mulai=today)
        t.shift = shift
        t.save(update_fields=["shift"])


@trainer_required
def manpower_list(request):
    query = request.GET.get("q", "").strip()
    manpower = Manpower.objects.filter(section_code=TARGET_DEPT_CODE)
    if query:
        manpower = manpower.filter(
            Q(employee_number__icontains=query) | Q(employee_name__icontains=query)
        )
    return render(request, "ai_parser/manpower_list.html", {
        "manpower": manpower,
        "query": query,
        "total": manpower.count(),
    })


@trainer_required
def upload_document(request):
    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["document"]
            suffix = Path(uploaded.name).suffix.lower()
            temp_path = None
            try:
                with NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    for chunk in uploaded.chunks():
                        tmp.write(chunk)
                    temp_path = tmp.name
                result = parse_docx(temp_path)
                request.session["manpower_import_preview"] = result
                request.session.modified = True
                return redirect("ai_parser:preview_import")
            except Exception as exc:
                logger.exception("Gagal memproses upload dokumen Word")
                form.add_error("document", f"Dokumen gagal diproses: {type(exc).__name__}: {exc}")
            finally:
                if temp_path and Path(temp_path).exists():
                    Path(temp_path).unlink()
    else:
        form = DocumentUploadForm()
    return render(request, "ai_parser/upload.html", {"form": form})


@trainer_required
def preview_import(request):
    result = request.session.get("manpower_import_preview")
    if not result:
        messages.warning(request, "Tidak ada hasil parsing. Silakan upload dokumen.")
        return redirect("ai_parser:upload_document")

    nomor = [row["employee_number"] for row in result["accepted"]]
    existing = set(Manpower.objects.filter(employee_number__in=nomor).values_list("employee_number", flat=True))
    existing |= {e.upper() for e in Trainee.objects.filter(emp_no__in=nomor).values_list("emp_no", flat=True)}
    for row in result["accepted"]:
        row["already_exists"] = row["employee_number"].upper() in existing
    return render(request, "ai_parser/preview.html", {"result": result})


@trainer_required
@require_POST
def confirm_import(request):
    result = request.session.get("manpower_import_preview")
    if not result:
        messages.error(request, "Sesi preview tidak ditemukan. Silakan upload ulang.")
        return redirect("ai_parser:upload_document")

    imported, duplicates, invalid, trainees = 0, 0, 0, 0
    doc_iso = (result.get("summary") or {}).get("join_date")
    with transaction.atomic():
        for row in result["accepted"]:
            if row.get("department_code") != TARGET_DEPT_CODE:
                invalid += 1
                continue
            raw_doc = row.get("doc") or doc_iso
            doc_date = date.fromisoformat(raw_doc) if raw_doc else None
            emp_no = row["employee_number"].strip().upper()
            if Manpower.objects.filter(employee_number=emp_no).exists():
                duplicates += 1
                continue
            try:
                with transaction.atomic():
                    Manpower.objects.create(
                        employee_number=emp_no,
                        employee_name=row["employee_name"],
                        doc=doc_date,
                        position=row.get("position", ""),
                        section_code="2700",
                        section="Haemo",
                        supervisor="",
                        shift=row.get("shift") or "Normal",
                        status=row.get("status", ""),
                        remarks=row.get("remarks", ""),
                    )
                    if _create_trainee(row, doc_date):
                        trainees += 1
                    imported += 1
            except IntegrityError:
                duplicates += 1

    request.session.pop("manpower_import_preview", None)
    log(request.user, "Parsing manpower", "Data manpower",
        f"Impor Word: {imported} disimpan ({trainees} masuk Trainee), {duplicates} duplikat, {invalid} tidak valid")
    messages.success(
        request,
        f"Import selesai. Berhasil: {imported}; duplikat dilewati: {duplicates}; baris tidak valid: {invalid}.",
    )
    return redirect("ai_parser:manpower_list")


@trainer_required
@require_POST
def update_assignment(request, pk):
    manpower = get_object_or_404(Manpower, pk=pk, section_code=TARGET_DEPT_CODE)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Request tidak valid."}, status=400)

    field = payload.get("field")
    value = str(payload.get("value", "")).strip()
    if field not in {"supervisor", "shift"}:
        return JsonResponse({"ok": False, "error": "Field tidak boleh diubah."}, status=400)
    if len(value) > 120:
        return JsonResponse({"ok": False, "error": "Nilai terlalu panjang."}, status=400)
    if field == "shift" and value not in {"Normal", "A", "B", "C", "Non-shift"}:
        return JsonResponse({"ok": False, "error": "Pilihan shift tidak valid."}, status=400)

    setattr(manpower, field, value)
    manpower.save(update_fields=[field, "updated_at"])
    if field == "shift":
        _sync_trainee_shift(manpower.employee_number, value)
    log(request.user, "Ubah data", "Manpower", f"{manpower.employee_number} {field} → {value or '-'}")
    return JsonResponse({"ok": True, "field": field, "value": value})


@trainer_required
def manpower_profile(request, pk):
    manpower = get_object_or_404(Manpower, pk=pk, section_code=TARGET_DEPT_CODE)
    return render(request, "ai_parser/profile.html", {"person": manpower})