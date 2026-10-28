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
from django.views.decorators.http import require_POST
from docx.opc.exceptions import PackageNotFoundError

from accounts.audit import log
from accounts.decorators import role_required
from master.models import Shift

from .forms import DocumentUploadForm
from .models import Manpower
from .word_parser import TARGET_DEPT_CODE, split_department, parse_docx, validate_record

logger = logging.getLogger(__name__)

# Halaman Manpower hanya untuk Super Admin dan Trainer.
staff_required = role_required("SUPER_ADMIN", "TRAINER")
MAX_ROWS = 2000
EXTRA_SHIFTS = ("Normal", "Non-shift")  # dipakai dokumen HR; tidak ada di master Shift


def shift_options():
    return list(EXTRA_SHIFTS) + list(Shift.objects.values_list("kode", flat=True))


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
    return render(request, "ai_parser/manpower_list.html", {
        "manpower": manpower,
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
                result = parse_docx(uploaded)
                # Hasil parsing hanya disimpan di sesi; belum masuk database sebelum dikonfirmasi.
                request.session["manpower_import_preview"] = result
                return redirect("ai_parser:preview_import")
            except ValueError as exc:  # tabel/header tidak ditemukan
                form.add_error("document", str(exc))
            except (PackageNotFoundError, BadZipFile):
                form.add_error("document", "File rusak atau bukan dokumen Word (.docx) yang valid.")
            except Exception:
                logger.exception("Gagal memproses upload dokumen Word: %s", uploaded.name)
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
    for item in rows:
        item["already_exists"] = item["record"]["employee_number"] in existing
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

    imported = duplicates = invalid = skipped = 0
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
                imported += 1
            except IntegrityError:
                logger.warning("Duplikat saat insert Emp No %s", rec["employee_number"])
                duplicates += 1

    request.session.pop("manpower_import_preview", None)
    detail = (f"{imported} disimpan, {duplicates} duplikat dilewati, {invalid} tidak valid, "
              f"{skipped} tidak dipilih (import dokumen Word)")
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
        log(request.user, "Ubah data", "Data Manpower Haemo",
            f"Emp No {manpower.employee_number}: {field} '{old}' -> '{value}'")
    return JsonResponse({"ok": True, "field": field, "value": value})


@staff_required
def manpower_profile(request, pk):
    manpower = get_object_or_404(Manpower, pk=pk, section_code=TARGET_DEPT_CODE)
    return render(request, "ai_parser/profile.html", {"person": manpower})
