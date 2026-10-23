from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from apps.accounts.models import StaffModule, User
from config.forms import TailwindFormMixin


class StaffLoginForm(TailwindFormMixin, AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser and user.user_type != User.UserType.STAFF:
            raise forms.ValidationError("This login is for staff accounts only.", code="inactive")


class StaffUserForm(TailwindFormMixin, forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput, required=False)
    modules = forms.MultipleChoiceField(
        choices=StaffModule.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Allowed modules",
    )

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "phone",
            "is_active",
            "access_mode",
            "profile_image",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["modules"].choices = StaffModule.choices
        self.fields["modules"].widget.attrs["class"] = (
            "h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
        )
        if self.instance.pk:
            self.fields["modules"].initial = self.instance.allowed_modules or []

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 or p2:
            if p1 != p2:
                raise forms.ValidationError("Passwords do not match.")
        elif not self.instance.pk:
            raise forms.ValidationError("Password is required for new users.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.user_type = User.UserType.STAFF
        user.is_staff = False
        password = self.cleaned_data.get("password1")
        if password:
            user.set_password(password)
        user.allowed_modules = self.cleaned_data.get("modules") or []
        if commit:
            user.save()
        return user


class UserModulePermissionForm(TailwindFormMixin, forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label="Staff user",
    )
    modules = forms.MultipleChoiceField(
        choices=StaffModule.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Allowed modules",
    )
    access_mode = forms.ChoiceField(
        choices=User.AccessMode.choices,
        initial=User.AccessMode.FULL,
        label="Access mode",
        help_text="Viewer accounts can open assigned screens only and cannot change data.",
    )

    def __init__(self, *args, **kwargs):
        selected_user = kwargs.pop("selected_user", None)
        super().__init__(*args, **kwargs)
        self.fields["modules"].choices = StaffModule.choices
        self.fields["modules"].widget.attrs["class"] = (
            "h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
        )
        self.fields["user"].queryset = User.objects.filter(
            user_type=User.UserType.STAFF,
            is_superuser=False,
        ).order_by("username")
        if selected_user:
            self.fields["user"].initial = selected_user
            self.fields["modules"].initial = selected_user.allowed_modules
            self.fields["access_mode"].initial = selected_user.access_mode

    def save(self):
        user = self.cleaned_data["user"]
        user.allowed_modules = self.cleaned_data["modules"]
        user.access_mode = self.cleaned_data["access_mode"]
        user.save(update_fields=["allowed_modules", "access_mode"])
        return user


class StaffPasswordChangeForm(TailwindFormMixin, PasswordChangeForm):
    pass
