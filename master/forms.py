from django import forms

from .models import Lini, Proses, Shift

REQ = {"required": "Isi data dengan lengkap"}
NUM = {"required": "Isi data dengan lengkap", "invalid": "Target dan durasi harus berupa angka",
       "min_value": "Target dan durasi harus berupa angka positif"}


class ProsesForm(forms.ModelForm):
    kode = forms.CharField(max_length=20, error_messages=REQ)
    nama = forms.CharField(max_length=100, error_messages=REQ)
    target_harian = forms.IntegerField(min_value=1, error_messages=NUM)
    durasi_maks_hari = forms.IntegerField(min_value=1, error_messages=NUM)

    class Meta:
        model = Proses
        fields = ["kode", "nama", "target_harian", "durasi_maks_hari"]

    def clean_kode(self):
        kode = self.cleaned_data["kode"].strip().upper()
        qs = Proses.objects.filter(kode__iexact=kode).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Kode proses sudah ada")
        return kode


class ShiftForm(forms.ModelForm):
    kode = forms.CharField(max_length=10, error_messages=REQ)
    nama = forms.CharField(max_length=60, error_messages=REQ)

    class Meta:
        model = Shift
        fields = ["kode", "nama"]

    def clean_kode(self):
        kode = self.cleaned_data["kode"].strip()
        if Shift.objects.filter(kode__iexact=kode).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Kode shift sudah ada")
        return kode


class LiniForm(forms.ModelForm):
    nama = forms.CharField(max_length=60, error_messages=REQ)
    lokasi = forms.CharField(max_length=120, error_messages=REQ)

    class Meta:
        model = Lini
        fields = ["nama", "lokasi"]

    def clean_nama(self):
        nama = self.cleaned_data["nama"].strip()
        if Lini.objects.filter(nama__iexact=nama).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Nama lini sudah ada")
        return nama
