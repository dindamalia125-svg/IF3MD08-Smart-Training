from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from datetime import datetime, time

from django.utils import timezone

from .audit import log
from .decorators import super_admin_required
from .forms import LoginForm, TrainerForm
from .models import AuditLog, User


def home(request):
    if request.user.is_authenticated:
        return redirect(request.user.home_url)
    return redirect("accounts:login")


def login_view(request):
    """UC-01: verifikasi kredensial & status akun, kenali peran, arahkan ke dashboard."""
    if request.user.is_authenticated:
        return redirect(request.user.home_url)
    form = LoginForm(request.POST or None)
    error = None
    if request.method == "POST":
        if form.is_valid():
            ident = form.cleaned_data["identifier"]
            candidate = User.objects.filter(Q(username__iexact=ident) | Q(email__iexact=ident)).first()
            # authenticate() menolak akun nonaktif -> pesan sama dengan kredensial salah
            user = authenticate(request, username=candidate.username, password=form.cleaned_data["password"]) if candidate else None
            if user is not None:
                login(request, user)
                if not form.cleaned_data["remember"]:
                    request.session.set_expiry(0)
                nxt = request.POST.get("next") or request.GET.get("next")
                if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
                    return redirect(nxt)
                return redirect(user.home_url)
        error = "Username atau Password Salah"
    return render(request, "accounts/login.html", {"form": form, "error": error, "next": request.GET.get("next", "")})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:login")


# ---------------------------------------------------------------- UC-02
@super_admin_required
def user_list(request, pk=None):
    """Daftar akun Trainer + panel Tambah/Ubah di sisi kanan."""
    instance = get_object_or_404(User, pk=pk, role=User.Role.TRAINER) if pk else None
    show_form = pk is not None or request.resolver_match.url_name == "user_add" or request.method == "POST"
    form = None
    if request.method == "POST":
        form = TrainerForm(request.POST, instance=instance)
        if form.is_valid():
            creating = instance is None
            user = form.save()
            log(request.user, "Tambah data" if creating else "Ubah data", "Akun Trainer",
                f"{user.username} {'dibuat' if creating else 'diperbarui'}")
            messages.success(request, "Data berhasil ditambahkan" if creating else "Data berhasil diperbarui")
            return redirect("accounts:user_list")
    elif show_form:
        form = TrainerForm(instance=instance)

    qs = User.objects.filter(role=User.Role.TRAINER).order_by("first_name", "username")
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if q:
        qs = qs.filter(Q(first_name__icontains=q) | Q(username__icontains=q) | Q(email__icontains=q))
    if status == "aktif":
        qs = qs.filter(is_active=True)
    elif status == "nonaktif":
        qs = qs.filter(is_active=False)
    page = Paginator(qs, 5).get_page(request.GET.get("page"))
    return render(request, "accounts/user_list.html",
                  {"page": page, "form": form, "editing": instance, "q": q, "status": status})


@super_admin_required
@require_POST
def user_toggle(request, pk):
    user = get_object_or_404(User, pk=pk, role=User.Role.TRAINER)
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    log(request.user, "Ubah data", "Akun Trainer", f"{user.username} {'diaktifkan' if user.is_active else 'dinonaktifkan'}")
    messages.success(request, f"Akun {user.username} {'diaktifkan' if user.is_active else 'dinonaktifkan'}")
    return redirect("accounts:user_list")


# ---------------------------------------------------------------- UC-05
def _parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


@super_admin_required
def audit_log(request):
    qs = AuditLog.objects.all().order_by("-waktu")
    dari = _parse_date(request.GET.get("dari"))
    sampai = _parse_date(request.GET.get("sampai"))
    tz = timezone.get_current_timezone()
    if dari:
        qs = qs.filter(waktu__gte=timezone.make_aware(datetime.combine(dari, time.min), tz))
    if sampai:
        qs = qs.filter(waktu__lte=timezone.make_aware(datetime.combine(sampai, time.max), tz))
    trainer = request.GET.get("trainer", "")
    if trainer:
        qs = qs.filter(username=trainer)
    jenis = request.GET.get("jenis", "")
    if jenis:
        qs = qs.filter(aktivitas=jenis)
    page = Paginator(qs, 10).get_page(request.GET.get("page"))
    trainers = User.objects.filter(role=User.Role.TRAINER).order_by("username").values_list("username", flat=True)
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "accounts/audit_log.html", {
        "page": page, "trainers": trainers, "aktivitas_list": AuditLog.AKTIVITAS,
        "dari": request.GET.get("dari", ""), "sampai": request.GET.get("sampai", ""),
        "trainer": trainer, "jenis": jenis, "querystring": params.urlencode(),
    })
