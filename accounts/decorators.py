from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect


def role_required(*roles):
    """Batasi view berdasarkan peran. Pengguna belum login diarahkan ke halaman masuk."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.role not in roles:
                messages.error(request, "Anda tidak memiliki akses ke halaman tersebut.")
                return redirect(request.user.home_url)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


super_admin_required = role_required("SUPER_ADMIN")
trainer_required = role_required("TRAINER")
