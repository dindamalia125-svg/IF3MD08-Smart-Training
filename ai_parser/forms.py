from pathlib import Path

from django import forms

MAX_UPLOAD_MB = 10
ALLOWED_EXTENSIONS = (".docx", ".pdf")
MAGIC = {".docx": b"PK\x03\x04", ".pdf": b"%PDF"}  # .docx adalah arsip ZIP; PDF diawali %PDF


class DocumentUploadForm(forms.Form):
    document = forms.FileField(
        label="Dokumen recruitment (Word / PDF)",
        error_messages={"required": "Pilih file dokumen Word (.docx) atau PDF terlebih dahulu.", "empty": "File kosong."},
    )

    def clean_document(self):
        file = self.cleaned_data["document"]
        ext = Path(file.name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError("Unggah file Word (.docx) atau PDF (.pdf).")
        if file.size > MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(f"Ukuran file maksimal {MAX_UPLOAD_MB} MB.")
        head = file.read(4)
        file.seek(0)
        if head != MAGIC[ext]:
            kind = "dokumen Word (.docx)" if ext == ".docx" else "PDF"
            raise forms.ValidationError(f"File rusak atau bukan {kind} yang valid.")
        return file
