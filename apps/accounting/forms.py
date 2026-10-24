from django import forms
from django.utils import timezone

from apps.accounting.models import Expense, OtherIncome, VendorPayment
from apps.vendors.models import Vendor
from config.forms import TailwindFormMixin

PAYMENT_ACCOUNT_CHOICES = (
    ("cash", "Cash"),
    ("bank", "Bank"),
    ("wallet", "Digital wallet"),
)


class ExpenseForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "category",
            "amount",
            "date",
            "payment_account",
            "reference",
            "description",
            "receipt",
        ]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_account"].widget = forms.Select(choices=PAYMENT_ACCOUNT_CHOICES)
        self.fields["payment_account"].initial = "cash"
        if not self.instance.pk:
            self.fields["date"].initial = timezone.localdate()


class OtherIncomeForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = OtherIncome
        fields = [
            "title",
            "amount",
            "date",
            "payment_account",
            "reference",
            "description",
            "attachment",
            "notes",
        ]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_account"].widget = forms.Select(choices=PAYMENT_ACCOUNT_CHOICES)
        self.fields["payment_account"].initial = "cash"
        if not self.instance.pk:
            self.fields["date"].initial = timezone.localdate()


class VendorPaymentForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = VendorPayment
        fields = ["vendor", "amount", "date", "payment_account", "reference"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vendor"].queryset = Vendor.objects.filter(is_active=True)
        if vendor is not None:
            self.fields["vendor"].queryset = Vendor.objects.filter(pk=vendor.pk)
            self.fields["vendor"].initial = vendor.pk
            self.fields["vendor"].widget = forms.HiddenInput()
        self.fields["payment_account"].widget = forms.Select(choices=PAYMENT_ACCOUNT_CHOICES)
        self.fields["payment_account"].initial = "cash"
        if not self.instance.pk:
            self.fields["date"].initial = timezone.localdate()
