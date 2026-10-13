from django import forms
from .models import User


class LoginForm(forms.Form):
    identifier = forms.CharField(
        max_length=254,
        strip=True,
        label="Username / Email",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "username atau email",
                "autocomplete": "username",
            }
        ),
        error_messages={
            "required": "Masukkan username atau email Anda."
        }
    )
    
    password = forms.CharField(
        strip=False,
        label="Kata Sandi",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Masukkan kata sandi",
                "autocomplete": "current-password",
            }
        ),
        error_messages={
            "required": "Masukkan kata sandi Anda."
        }
    )
    
    remember = forms.BooleanField(
        required=False,
        label="Ingat saya",
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input"
            }
        )
    )


class TrainerForm(forms.Form):
    """Form tambah/ubah akun Trainer"""

    nama_lengkap = forms.CharField(
        max_length=150, 
        error_messages={"required": "Isi data dengan lengkap"}
    )
    username = forms.CharField(
        max_length=150, 
        error_messages={"required": "Isi data dengan lengkap"}
    )
    email = forms.EmailField(
        error_messages={
            "required": "Isi data dengan lengkap", 
            "invalid": "Gunakan format email dengan benar"
        }
    )
    password = forms.CharField(
        required=False, 
        widget=forms.PasswordInput(render_value=False), 
        min_length=8,
        error_messages={"min_length": "Kata sandi minimal 8 karakter"}
    )
    is_active = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        if instance and not self.is_bound:
            self.initial = {
                "nama_lengkap": instance.get_full_name(),
                "username": instance.username,
                "email": instance.email,
                "is_active": instance.is_active,
            }

    def clean_username(self):
        value = self.cleaned_data["username"].strip()
        qs = User.objects.filter(username__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Username sudah digunakan (akun sudah ada)")
        return value

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        qs = User.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Email sudah digunakan (akun sudah ada)")
        return value

    def clean(self):
        data = super().clean()
        if not self.instance and not data.get("password") and "password" not in self.errors:
            self.add_error("password", "Isi data dengan lengkap")
        return data

    def save(self):
        d = self.cleaned_data
        user = self.instance or User(role=User.Role.TRAINER)
        user.first_name = d["nama_lengkap"].strip()
        user.last_name = ""
        user.username = d["username"]
        user.email = d["email"]
        user.is_active = d["is_active"]
        if d.get("password"):
            user.set_password(d["password"])
        user.save()
        return user