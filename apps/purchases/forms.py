from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from apps.inventory.models import Warehouse
from apps.inventory.services import get_default_warehouse
from apps.products.models import Product
from apps.purchases.models import GRN, GRNItem
from config.forms import TailwindFormMixin


class GRNForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = GRN
        fields = ["vendor", "invoice_number", "warehouse"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["invoice_number"].required = False
        self.fields["invoice_number"].help_text = "Optional vendor invoice / bill number"
        self.fields["warehouse"].queryset = Warehouse.objects.filter(is_active=True)
        if not self.instance.pk:
            self.fields["warehouse"].initial = get_default_warehouse()

    def save(self, commit=True):
        grn = super().save(commit=False)
        if not grn.pk:
            grn.grn_date = timezone.localdate()
            grn.status = GRN.Status.PENDING
        if commit:
            grn.save()
        return grn


class GRNItemForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = GRNItem
        fields = ["product", "quantity", "purchase_rate", "batch_number", "expiry_date"]
        labels = {
            "product": "Item name",
            "quantity": "Qty",
            "purchase_rate": "Purchase rate",
            "batch_number": "Batch number",
            "expiry_date": "Expiry date",
        }
        widgets = {"expiry_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(is_active=True).order_by("name")
        self.fields["batch_number"].required = False
        self.fields["expiry_date"].required = False
        self.fields["quantity"].widget.attrs["min"] = "1"
        self.fields["purchase_rate"].widget.attrs["min"] = "0"


GRNItemFormSet = inlineformset_factory(
    GRN,
    GRNItem,
    form=GRNItemForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)
