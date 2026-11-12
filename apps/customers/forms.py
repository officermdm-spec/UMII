import logging
import re
import threading
from smtplib import SMTPException

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm, UserCreationForm

from apps.accounts.models import User
from apps.customers.models import Address, CustomerProfile
from config.forms import TailwindFormMixin

logger = logging.getLogger(__name__)

DISPOSABLE_EMAIL_DOMAINS = frozenset(
    {
        "10minutemail.com",
        "getnada.com",
        "guerrillamail.com",
        "mailinator.com",
        "merepost.com",
        "temp-mail.org",
        "throwawaymail.com",
        "yopmail.com",
    }
)
SPAM_URL_PATTERN = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)


class CustomerRegistrationForm(TailwindFormMixin, UserCreationForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    phone = forms.CharField(max_length=20)
    website = forms.CharField(
        required=False,
        label="Website",
        widget=forms.HiddenInput(
            attrs={"autocomplete": "off", "tabindex": "-1", "aria-hidden": "true"}
        ),
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "username", "password1", "password2"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        domain = email.rsplit("@", 1)[1]
        if any(
            domain == disposable_domain or domain.endswith(f".{disposable_domain}")
            for disposable_domain in DISPOSABLE_EMAIL_DOMAINS
        ):
            raise forms.ValidationError("Please use a non-temporary email address.")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("website"):
            raise forms.ValidationError("Unable to process registration.")

        for field_name in ("first_name", "last_name", "email", "phone", "username"):
            value = cleaned_data.get(field_name)
            if isinstance(value, str) and SPAM_URL_PATTERN.search(value):
                self.add_error(field_name, "URLs are not allowed in this field.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.phone = self.cleaned_data["phone"]
        user.user_type = User.UserType.CUSTOMER
        if commit:
            user.save()
        return user


class CustomerLoginForm(TailwindFormMixin, AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email or username"

    def clean(self):
        username = self.cleaned_data.get("username")
        if username and "@" in username:
            customer = User.objects.filter(
                email__iexact=username,
                user_type=User.UserType.CUSTOMER,
            ).first()
            if customer:
                self.cleaned_data["username"] = customer.get_username()
        return super().clean()

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.user_type != User.UserType.CUSTOMER:
            raise forms.ValidationError(
                "This login is for customer accounts only.",
                code="invalid_login",
            )


class CustomerPasswordResetForm(TailwindFormMixin, PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].label = "Email address"
        self.fields["email"].widget.attrs.update(
            {
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }
        )

    def get_users(self, email):
        return User._default_manager.filter(
            email__iexact=email,
            is_active=True,
            user_type=User.UserType.CUSTOMER,
        ).iterator()

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        def _deliver():
            try:
                super(CustomerPasswordResetForm, self).send_mail(
                    subject_template_name,
                    email_template_name,
                    context,
                    from_email,
                    to_email,
                    html_email_template_name=html_email_template_name,
                )
                logger.info("Password reset email accepted by the configured email backend")
            except (SMTPException, OSError, TimeoutError):
                logger.exception("Password reset email was not delivered to %s", to_email)

        backend = settings.EMAIL_BACKEND
        if "HttpsEmail" in backend or any(name in backend for name in ("locmem", "dummy", "console")):
            _deliver()
        else:
            threading.Thread(target=_deliver, daemon=True).start()


class CustomerSetPasswordForm(TailwindFormMixin, SetPasswordForm):
    pass


class CustomerProfileForm(TailwindFormMixin, forms.ModelForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    class Meta:
        model = CustomerProfile
        fields = [ "date_of_birth","phone","profile_image"]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
        }
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["first_name"].initial = self.user.first_name
        self.fields["last_name"].initial = self.user.last_name
        self.fields["email"].initial = self.user.email
        self.order_fields(["first_name", "last_name", "email", "phone", "date_of_birth", "profile_image"])

    def save(self, commit=True):
        profile = super().save(commit=False)
        self.user.first_name = self.cleaned_data["first_name"]
        self.user.last_name = self.cleaned_data["last_name"]
        self.user.email = self.cleaned_data["email"]
        self.user.phone = self.cleaned_data.get("phone", self.user.phone)
        if commit:
            self.user.save()
            profile.save()
        return profile


class StaffCustomerForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "is_active"]


class AddressForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Address
        fields = ["full_name", "phone", "address", "city", "area", "postal_code", "is_default"]
