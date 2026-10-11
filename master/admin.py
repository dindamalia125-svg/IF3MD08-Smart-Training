from django.contrib import admin

from .models import Lini, Proses, Shift

admin.site.register(Proses)
admin.site.register(Shift)
admin.site.register(Lini)
