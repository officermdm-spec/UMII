from django import forms

from apps.payments.models import Payment, PaymentMethod
from config.forms import TailwindFormMixin


class PaymentMethodForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = ["code", "name", "description", "is_active",]


class PaymentStatusForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["status", "transaction_id"]
