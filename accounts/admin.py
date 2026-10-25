from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AuditLog, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "employee_no", "email", "first_name", "role", "is_active")
    list_filter = ("role", "is_active")
    fieldsets = UserAdmin.fieldsets + (("Peran", {"fields": ("employee_no", "role")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Peran", {"fields": ("email", "employee_no", "role")}),)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("waktu", "username", "aktivitas", "objek", "keterangan")
    list_filter = ("aktivitas",)
    search_fields = ("username", "keterangan")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
