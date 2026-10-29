from django import forms

from apps.customers.models import Address
from apps.orders.models import Order
from apps.payments.models import PaymentMethod
from config.forms import TailwindFormMixin
from config.validators import validate_upload_image


class CheckoutForm(TailwindFormMixin, forms.Form):
    billing_address = forms.ModelChoiceField(queryset=Address.objects.none(), required=False)
    shipping_address = forms.ModelChoiceField(queryset=Address.objects.none(), required=False)
    same_as_billing = forms.BooleanField(required=False, initial=True)
    payment_method = forms.ModelChoiceField(queryset=PaymentMethod.objects.filter(is_active=True))
    payment_proof = forms.ImageField(
        required=False,
        help_text="Upload a payment screenshot for online / wallet / bank payments.",
        validators=[validate_upload_image],
    )
    notes = forms.CharField(required=False, widget=forms.Textarea)
    full_name = forms.CharField(max_length=150, required=False, label="Full name")
    email = forms.EmailField(required=False)
    phone = forms.CharField(max_length=20, required=False)
    address = forms.CharField(required=False, widget=forms.Textarea)
    city = forms.CharField(max_length=100, required=False)
    area = forms.CharField(max_length=100, required=False)
    postal_code = forms.CharField(max_length=20, required=False)

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.is_guest = user is None
        if self.is_guest:
            self.fields.pop("billing_address")
            self.fields.pop("shipping_address")
            self.fields.pop("same_as_billing")
            for name in ("full_name", "email", "phone", "address", "city"):
                self.fields[name].required = True
        else:
            for name in ("full_name", "email", "phone", "address", "city", "area", "postal_code"):
                self.fields.pop(name)
            addresses = Address.objects.filter(user=user)
            self.fields["billing_address"].queryset = addresses
            self.fields["shipping_address"].queryset = addresses
            self.fields["billing_address"].required = True
            self.fields["shipping_address"].required = True
            default = addresses.filter(is_default=True).first()
            if default:
                self.fields["billing_address"].initial = default
                self.fields["shipping_address"].initial = default

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("payment_method")
        proof = cleaned.get("payment_proof")
        if method and method.code != PaymentMethod.Code.COD and not proof:
            self.add_error(
                "payment_proof",
                "Please upload a payment screenshot for online payment methods.",
            )
        if method and method.code == PaymentMethod.Code.COD:
            cleaned["payment_proof"] = None
        return cleaned


class OrderTrackingForm(forms.Form):
    order_number = forms.CharField(max_length=30, label="Order number")

    def clean_order_number(self):
        return self.cleaned_data["order_number"].strip().upper()


class CartUpdateForm(forms.Form):
    quantity = forms.IntegerField(min_value=0)


class OrderStatusForm(TailwindFormMixin, forms.Form):
    status = forms.ChoiceField()
    note = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        choices = kwargs.pop("choices")
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = choices


class OrderPaymentStatusForm(TailwindFormMixin, forms.Form):
    payment_status = forms.ChoiceField(choices=Order.PaymentStatus.choices)
    transaction_id = forms.CharField(required=False, label="Transaction ID")
    note = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        current = kwargs.pop("current", None)
        super().__init__(*args, **kwargs)
        if current:
            self.fields["payment_status"].initial = current
