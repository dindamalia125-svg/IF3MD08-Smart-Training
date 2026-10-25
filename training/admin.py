from django.contrib import admin

from .models import Capaian, ProsesTrainee, RiwayatShift, Sertifikat, Trainee


class ProsesInline(admin.TabularInline):
    model = ProsesTrainee
    extra = 0


@admin.register(Trainee)
class TraineeAdmin(admin.ModelAdmin):
    list_display = ("emp_no", "nama", "shift", "lini", "kontrak_berakhir", "aktif")
    search_fields = ("emp_no", "nama")
    inlines = [ProsesInline]


admin.site.register(Capaian)
admin.site.register(RiwayatShift)
admin.site.register(Sertifikat)
