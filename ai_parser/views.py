import json
import logging
from datetime import date
from zipfile import BadZipFile

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from docx.opc.exceptions import PackageNotFoundError

from accounts.audit import log
from accounts.decorators import role_required
from master.models import Shift
from training.models import RiwayatShift, Trainee

from .forms import DocumentUploadForm
from .models import Manpower
from .pdf_parser import parse_pdf
from .word_parser import TARGET_DEPT_CODE, split_department, parse_docx, validate_record

logger = logging.getLogger(__name__)

# Halaman Manpower hanya untuk Super Admin dan Trainer.
staff_required = role_required("SUPER_ADMIN", "TRAINER")
MAX_ROWS = 2000
EXTRA_SHIFTS = ("Normal", "Non-shift")  # dipakai dokumen HR; tidak ada di master Shift


def shift_options():
    return list(EXTRA_SHIFTS) + list(Shift.objects.values_list("kode", flat=True))


def _create_trainee(rec, doc_date):
    """Buat Trainee + RiwayatShift dari data impor. Return True bila dibuat."""
    emp_no = rec["employee_number"].strip().upper()
    if Trainee.objects.filter(emp_no__iexact=emp_no).exists():
        return False
    shift = Shift.objects.filter(kode__iexact=(rec.get("shift") or "").strip()).first()
    mulai = doc_date or timezone.localdate()
    trainee = Trainee.objects.create(emp_no=emp_no, nama=rec["employee_name"], shift=shift, mulai_training=mulai)
    if shift:
        RiwayatShift.objects.create(trainee=trainee, shift=shift, mulai=mulai)
    return True


def _sync_trainee_shift(emp_no, kode):
    """Samakan shift Trainee dengan perubahan shift di Manpower (riwayat shift ikut dicatat)."""
    trainee = Trainee.objects.filter(emp_no__iexact=emp_no).first()
    shift = Shift.objects.filter(kode__iexact=kode).first()
    if not trainee or not shift or trainee.shift_id == shift.pk:
        return
    today = timezone.localdate()
    with transaction.atomic():
        trainee.riwayat_shift.filter(selesai__isnull=True).update(selesai=today)
        RiwayatShift.objects.create(trainee=trainee, shift=shift, lini=trainee.lini, mulai=today)
        trainee.shift = shift
        trainee.save(update_fields=["shift"])


@staff_required
def manpower_list(request):
    query = request.GET.get("q", "").strip()
    manpower = Manpower.objects.filter(section_code=TARGET_DEPT_CODE)
    if query:
        manpower = manpower.filter(Q(employee_number__icontains=query) | Q(employee_name__icontains=query))
    supervisors = (
        Manpower.objects.exclude(supervisor="").order_by("supervisor")
        .values_list("supervisor", flat=True).distinct()
    )
    people = list(manpower)
    # Kontrak berakhir disimpan pada Trainee (sumber data yang sama dengan notifikasi finish kontrak).
    contracts = {
        t.emp_no.upper(): t.kontrak_berakhir
        for t in Trainee.objects.filter(emp_no__in=[p.employee_number for p in people])
    }
    for p in people:
        p.has_trainee = p.employee_number.upper() in contracts
        p.kontrak = contracts.get(p.employee_number.upper())
    return render(request, "ai_parser/manpower_list.html", {
        "manpower": people,
        "query": query,
        "total": manpower.count(),
        "shift_options": shift_options(),
        "supervisor_options": list(supervisors),
    })


@staff_required
def upload_document(request):
    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["document"]
            try:
                uploaded.seek(0)
                is_pdf = uploaded.name.lower().endswith(".pdf")
                result = parse_pdf(uploaded) if is_pdf else parse_docx(uploaded)
                # Hasil parsing hanya disimpan di sesi; belum masuk database sebelum dikonfirmasi.
                request.session["manpower_import_preview"] = result
                return redirect("ai_parser:preview_import")
            except ValueError as exc:  # tabel/header tidak ditemukan
                form.add_error("document", str(exc))
            except (PackageNotFoundError, BadZipFile):
                form.add_error("document", "File rusak atau bukan dokumen Word (.docx) yang valid.")
            except Exception:
                logger.exception("Gagal memproses upload dokumen: %s", uploaded.name)
                form.add_error("document", "Dokumen gagal diproses. Periksa isi file atau hubungi admin.")
    else:
        form = DocumentUploadForm()
    return render(request, "ai_parser/upload.html", {"form": form})


@staff_required
def preview_import(request):
    result = request.session.get("manpower_import_preview")
    if not result:
        messages.warning(request, "Tidak ada hasil parsing. Silakan upload dokumen.")
        return redirect("ai_parser:upload_document")

    # Satu tabel yang dapat diedit: baris valid dan baris yang perlu diperbaiki.
    rows = [{"record": r, "reason": ""} for r in result["accepted"]] + result["needs_review"]
    rows.sort(key=lambda item: item["record"].get("source_row") or 0)
    existing = set(
        Manpower.objects.filter(employee_number__in=[i["record"]["employee_number"] for i in rows])
        .values_list("employee_number", flat=True)
    )
    existing |= {  # Emp No yang sudah menjadi Trainee juga ditandai duplikat
        e.upper() for e in Trainee.objects.filter(
            emp_no__in=[i["record"]["employee_number"] for i in rows]).values_list("emp_no", flat=True)
    }
    for item in rows:
        item["already_exists"] = item["record"]["employee_number"].upper() in existing
        item["checked"] = not item["reason"] and not item["already_exists"]
    return render(request, "ai_parser/preview.html", {
        "result": result, "rows": rows, "shift_options": shift_options(),
    })


@staff_required
@require_POST
def confirm_import(request):
    if not request.session.get("manpower_import_preview"):
        messages.error(request, "Sesi preview tidak ditemukan. Silakan upload ulang.")
        return redirect("ai_parser:upload_document")
    try:
        count = min(int(request.POST.get("count", "0")), MAX_ROWS)
    except ValueError:
        count = 0

    imported = duplicates = invalid = skipped = trainees = 0
    seen: set = set()
    with transaction.atomic():
        for i in range(count):
            if request.POST.get(f"pilih-{i}") != "1":
                skipped += 1
                continue
            code, name = split_department(request.POST.get(f"department-{i}", ""))
            # Data hasil edit pengguna divalidasi ulang oleh aturan yang sama dengan parser.
            rec, reasons = validate_record({
                "employee_number": request.POST.get(f"employee_number-{i}", ""),
                "employee_name": request.POST.get(f"employee_name-{i}", ""),
                "department_code": code, "department_name": name,
                "doc": request.POST.get(f"doc-{i}", ""),
                "position": request.POST.get(f"position-{i}", ""),
                "shift": request.POST.get(f"shift-{i}", ""),
                "status": request.POST.get(f"status-{i}", ""),
                "remarks": request.POST.get(f"remarks-{i}", ""),
            }, seen)
            if reasons:
                if reasons == ["Emp No duplikat dalam file"]:
                    duplicates += 1
                else:
                    invalid += 1
                continue
            rec["employee_number"] = rec["employee_number"].upper()
            if Manpower.objects.filter(employee_number=rec["employee_number"]).exists():
                duplicates += 1
                continue
            try:
                with transaction.atomic():
                    Manpower.objects.create(
                        employee_number=rec["employee_number"],
                        employee_name=rec["employee_name"],
                        doc=date.fromisoformat(rec["doc"]) if rec["doc"] else None,
                        position=rec["position"],
                        section_code=TARGET_DEPT_CODE,
                        section="Haemo",
                        supervisor="",
                        shift=rec["shift"],
                        status=rec["status"],
                        remarks=rec["remarks"],
                    )
                    if _create_trainee(rec, date.fromisoformat(rec["doc"]) if rec["doc"] else None):
                        trainees += 1
                imported += 1
            except IntegrityError:
                logger.warning("Duplikat saat insert Emp No %s", rec["employee_number"])
                duplicates += 1

    request.session.pop("manpower_import_preview", None)
    detail = (f"{imported} disimpan ({trainees} masuk Trainee), {duplicates} duplikat dilewati, {invalid} tidak valid, "
              f"{skipped} tidak dipilih (import dokumen Word/PDF)")
    log(request.user, "Parsing manpower", "Data Manpower Haemo", detail)
    logger.info("Import manpower oleh %s: %s", request.user.username, detail)
    messages.success(
        request,
        f"Import selesai. Berhasil: {imported}; duplikat dilewati: {duplicates}; "
        f"tidak valid: {invalid}; tidak dipilih: {skipped}.",
    )
    return redirect("ai_parser:manpower_list")


@login_required
@require_POST
def update_assignment(request, pk):
    # Endpoint JSON: kegagalan akses dijawab 403 JSON, bukan redirect HTML.
    if request.user.role not in ("SUPER_ADMIN", "TRAINER"):
        return JsonResponse({"ok": False, "error": "Akses hanya untuk Super Admin dan Trainer."}, status=403)
    manpower = get_object_or_404(Manpower, pk=pk, section_code=TARGET_DEPT_CODE)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Request tidak valid."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "error": "Request tidak valid."}, status=400)

    field = payload.get("field")
    value = str(payload.get("value", "")).strip()
    if field == "kontrak_berakhir":
        return _update_contract(request, manpower, value)
    if field not in {"supervisor", "shift"}:
        return JsonResponse({"ok": False, "error": "Field tidak boleh diubah."}, status=400)
    if len(value) > 120:
        return JsonResponse({"ok": False, "error": "Nilai terlalu panjang."}, status=400)
    if field == "shift" and value not in shift_options():
        return JsonResponse({"ok": False, "error": "Pilihan shift tidak valid."}, status=400)

    old = getattr(manpower, field)
    if old != value:
        setattr(manpower, field, value)
        manpower.save(update_fields=[field, "updated_at"])
        if field == "shift":
            _sync_trainee_shift(manpower.employee_number, value)
        log(request.user, "Ubah data", "Data Manpower Haemo",
            f"Emp No {manpower.employee_number}: {field} '{old}' -> '{value}'")
    return JsonResponse({"ok": True, "field": field, "value": value})


def _update_contract(request, manpower, value):
    """Isi/hapus tanggal finish kontrak. Disimpan pada Trainee dengan Emp No yang sama."""
    trainee = Trainee.objects.filter(emp_no__iexact=manpower.employee_number).first()
    if not trainee:
        return JsonResponse({"ok": False, "error": "Karyawan belum terdaftar sebagai Trainee."}, status=400)
    new = None
    if value:
        try:
            new = date.fromisoformat(value)
        except ValueError:
            return JsonResponse({"ok": False, "error": "Format tanggal tidak valid."}, status=400)
        if not 2000 <= new.year <= 2100:
            return JsonResponse({"ok": False, "error": "Tanggal kontrak di luar rentang wajar."}, status=400)
    old = trainee.kontrak_berakhir
    if old != new:
        trainee.kontrak_berakhir = new
        trainee.save(update_fields=["kontrak_berakhir"])
        log(request.user, "Ubah data", "Data Manpower Haemo",
            f"Emp No {manpower.employee_number}: kontrak berakhir '{old or '-'}' -> '{new or '-'}'")
    return JsonResponse({"ok": True, "field": "kontrak_berakhir", "value": value})


@staff_required
@require_POST
def delete_manpower(request, pk):
    """Hapus satu baris Manpower. Data Trainee (capaian, sertifikat) sengaja tidak ikut dihapus."""
    manpower = get_object_or_404(Manpower, pk=pk, section_code=TARGET_DEPT_CODE)
    label = f"{manpower.employee_number} {manpower.employee_name}"
    manpower.delete()
    log(request.user, "Hapus data", "Data Manpower Haemo", f"Hapus Emp No {label}")
    logger.info("Manpower dihapus oleh %s: %s", request.user.username, label)
    messages.success(request, f"Data {label} dihapus dari Manpower Data. Riwayat training tetap tersimpan.")
    return redirect("ai_parser:manpower_list")


@staff_required
def manpower_profile(request, pk):
    manpower = get_object_or_404(Manpower, pk=pk, section_code=TARGET_DEPT_CODE)
    return render(request, "ai_parser/profile.html", {"person": manpower})
