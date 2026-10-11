from django import forms
from django.utils import timezone

from master.models import Proses

from .models import Trainee


class CapaianForm(forms.Form):
    trainee = forms.ModelChoiceField(Trainee.objects.filter(aktif=True), error_messages={
        "required": "Pilih trainee", "invalid_choice": "Pilih trainee"})
    proses = forms.ModelChoiceField(Proses.objects.all(), error_messages={
        "required": "Pilih kode proses kerja", "invalid_choice": "Pilih kode proses kerja"})
    tanggal = forms.DateField(initial=timezone.localdate, error_messages={"required": "Isi tanggal", "invalid": "Tanggal tidak valid"})
    output = forms.IntegerField(min_value=0, error_messages={
        "required": "Isian wajib berupa angka dan tidak negatif",
        "invalid": "Isian wajib berupa angka dan tidak negatif",
        "min_value": "Isian wajib berupa angka dan tidak negatif"})
    reject = forms.IntegerField(min_value=0, error_messages={
        "required": "Isian wajib berupa angka dan tidak negatif",
        "invalid": "Isian wajib berupa angka dan tidak negatif",
        "min_value": "Isian wajib berupa angka dan tidak negatif"})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # queryset dievaluasi saat form dibuat agar selalu terbaru
        self.fields["trainee"].queryset = Trainee.objects.filter(aktif=True).order_by("badge")
        self.fields["proses"].queryset = Proses.objects.all()

    def first_error(self):
        for field in ("trainee", "proses", "tanggal", "output", "reject"):
            errs = self.errors.get(field)
            if errs:
                return errs[0]
        return None
