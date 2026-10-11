from .models import AuditLog


def log(user, aktivitas, objek, keterangan=""):
    """Catat aktivitas dengan timestamp dan ID pelaksana (dipanggil oleh semua use case yang mengubah data)."""
    return AuditLog.objects.create(
        user=user if getattr(user, "pk", None) else None,
        username=getattr(user, "username", "") or "",
        aktivitas=aktivitas,
        objek=objek,
        keterangan=keterangan[:300],
    )
