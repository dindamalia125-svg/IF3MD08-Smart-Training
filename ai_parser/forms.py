from pathlib import Path

from django import forms

MAX_UPLOAD_MB = 10
DOCX_MAGIC = b"PK\x03\x04"  # .docx adalah arsip ZIP


class DocumentUploadForm(forms.Form):
    document = forms.FileField(
        label="Dokumen recruitment (DOCX)",
        error_messages={"required": "Pilih file dokumen Word (.docx) terlebih dahulu.", "empty": "File kosong."},
    )

    def clean_document(self):
        file = self.cleaned_data["document"]
        if Path(file.name).suffix.lower() != ".docx":
            raise forms.ValidationError("Unggah file Word dengan ekstensi .docx.")
        if file.size > MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(f"Ukuran file maksimal {MAX_UPLOAD_MB} MB.")
        head = file.read(4)
        file.seek(0)
        if head != DOCX_MAGIC:
            raise forms.ValidationError("File rusak atau bukan dokumen Word (.docx) yang valid.")
        return file
