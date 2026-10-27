import json
import logging
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import DocumentUploadForm
from .models import Manpower
from .word_parser import TARGET_DEPT_CODE, parse_docx

logger = logging.getLogger(__name__)


def user_has_import_access(user):
    # Adapt this to the role field used by the existing STA project.
    role = str(
        getattr(user, "role", "") or getattr(user, "user_type", "")
    ).strip().lower().replace(" ", "_")
    return user.is_authenticated and (
        user.is_superuser or role in {"super_admin", "superadmin", "trainer"}
    )


def require_sta_role(user):
    if not user_has_import_access(user):
        raise PermissionDenied("Akses hanya untuk Super Admin dan Trainer.")


@login_required
def manpower_list(request):
    require_sta_role(request.user)
    query = request.GET.get("q", "").strip()
    manpower = Manpower.objects.filter(section_code=TARGET_DEPT_CODE)
    if query:
        manpower = manpower.filter(
            Q(employee_number__icontains=query) |
            Q(employee_name__icontains=query)
        )
    return render(request, "ai_parser/manpower_list.html", {
        "manpower": manpower,
        "query": query,
        "total": manpower.count(),
    })


@login_required
def upload_document(request):
    require_sta_role(request.user)
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
                # Store parsed preview in session; do not persist manpower until confirmation.
                request.session["manpower_import_preview"] = result
                request.session.modified = True
                return redirect("ai_parser:preview_import")
            except Exception as exc:
                # FIX: Indentasi diperbaiki agar masuk dalam blok except
                logger.exception("Gagal memproses upload dokumen Word")
                form.add_error(
                    "document",
                    f"Dokumen gagal diproses: {type(exc).__name__}: {exc}",
                )
            finally:
                if temp_path and Path(temp_path).exists():
                    Path(temp_path).unlink()
    else:
        form = DocumentUploadForm()
    return render(request, "ai_parser/upload.html", {"form": form})


@login_required
def preview_import(request):
    require_sta_role(request.user)
    result = request.session.get("manpower_import_preview")
    if not result:
        messages.warning(request, "Tidak ada hasil parsing. Silakan upload dokumen.")
        return redirect("ai_parser:upload_document")
    
    # Mark candidates already present in database, so the user can see them before import.
    existing = set(
        Manpower.objects.filter(
            employee_number__in=[
                row["employee_number"] for row in result["accepted"]
            ]
        ).values_list("employee_number", flat=True)
    )
    for row in result["accepted"]:
        row["already_exists"] = row["employee_number"] in existing
    return render(request, "ai_parser/preview.html", {"result": result})


@login_required
@require_POST
def confirm_import(request):
    require_sta_role(request.user)
    result = request.session.get("manpower_import_preview")
    if not result:
        messages.error(request, "Sesi preview tidak ditemukan. Silakan upload ulang.")
        return redirect("ai_parser:upload_document")

    imported, duplicates, invalid = 0, 0, 0
    with transaction.atomic():
        for row in result["accepted"]:
            if row.get("department_code") != TARGET_DEPT_CODE:
                invalid += 1
                continue
            if Manpower.objects.filter(employee_number=row["employee_number"]).exists():
                duplicates += 1
                continue
            try:
                # FIX: Sub-transaction per iterasi untuk menangani IntegrityError secara aman
                with transaction.atomic():
                    Manpower.objects.create(
                        employee_number=row["employee_number"],
                        employee_name=row["employee_name"],
                        doc=date.fromisoformat(row["doc"]) if row.get("doc") else None,
                        position=row.get("position", ""),
                        section_code="2700",
                        section="Haemo",
                        supervisor="",
                        shift=row.get("shift") or "Normal",
                        status=row.get("status", ""),
                        remarks=row.get("remarks", ""),
                    )
                    imported += 1
            except IntegrityError:
                # Handles a concurrent duplicate insert without failing the outer transaction.
                duplicates += 1

    request.session.pop("manpower_import_preview", None)
    messages.success(
        request,
        f"Import selesai. Berhasil: {imported}; duplikat dilewati: {duplicates}; baris tidak valid: {invalid}.",
    )
    return redirect("ai_parser:manpower_list")


@login_required
@require_POST
def update_assignment(request, pk):
    require_sta_role(request.user)
    manpower = get_object_or_404(Manpower, pk=pk, section_code=TARGET_DEPT_CODE)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Request tidak valid."}, status=400)

    allowed_fields = {"supervisor", "shift"}
    field = payload.get("field")
    value = str(payload.get("value", "")).strip()
    if field not in allowed_fields:
        return JsonResponse({"ok": False, "error": "Field tidak boleh diubah."}, status=400)
    if len(value) > 120:
        return JsonResponse({"ok": False, "error": "Nilai terlalu panjang."}, status=400)

    # Replace these example options with the official Haemo master lists.
    if field == "shift" and value not in {"Normal", "A", "B", "C", "Non-shift"}:
        return JsonResponse({"ok": False, "error": "Pilihan shift tidak valid."}, status=400)

    setattr(manpower, field, value)
    manpower.save(update_fields=[field, "updated_at"])
    return JsonResponse({"ok": True, "field": field, "value": value})


@login_required
def manpower_profile(request, pk):
    require_sta_role(request.user)
    manpower = get_object_or_404(Manpower, pk=pk, section_code=TARGET_DEPT_CODE)
    return render(request, "ai_parser/profile.html", {"person": manpower})