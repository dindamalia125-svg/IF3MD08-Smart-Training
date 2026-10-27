from pathlib import Path
from django import forms


class DocumentUploadForm(forms.Form):
    document = forms.FileField(label="Dokumen recruitment (DOCX)")

    def clean_document(self):
        file = self.cleaned_data["document"]
        if Path(file.name).suffix.lower() != ".docx":
            raise forms.ValidationError("Untuk versi awal, unggah file Word .docx.")
        if file.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Ukuran file maksimal 10 MB.")
        return file
