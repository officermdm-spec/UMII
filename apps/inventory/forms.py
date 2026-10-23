from django import forms

from apps.inventory.models import StockTransaction, Warehouse
from apps.inventory.services import available_stock
from apps.products.models import Product
from config.forms import TailwindFormMixin


class WarehouseForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ["name", "code", "address", "is_active"]

    def clean_code(self):
        return (self.cleaned_data.get("code") or "").strip().upper()


class StockAdjustmentForm(TailwindFormMixin, forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.filter(is_active=True))
    warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.filter(is_active=True))
    quantity = forms.IntegerField(
        help_text="Positive adds stock. Negative reduces stock. Damage must be negative."
    )
    transaction_type = forms.ChoiceField(
        choices=[
            (StockTransaction.Type.ADJUSTMENT, "Stock Adjustment"),
            (StockTransaction.Type.DAMAGE, "Damage (use negative qty)"),
            (StockTransaction.Type.CORRECTION, "Manual Correction"),
        ]
    )
    min_stock_level = forms.IntegerField(
        required=False,
        min_value=0,
        label="Minimum stock level",
        help_text="Optional. Updates the product reorder point used for Low stock alerts.",
    )
    notes = forms.CharField(required=False, widget=forms.Textarea)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        product = self.initial.get("product") or self.data.get("product")
        warehouse = self.initial.get("warehouse") or self.data.get("warehouse")
        if product:
            try:
                instance = Product.objects.get(pk=product)
            except (Product.DoesNotExist, ValueError, TypeError):
                instance = None
            if instance:
                self.fields["min_stock_level"].initial = instance.min_stock_level
                selected = None
                if warehouse:
                    selected = Warehouse.objects.filter(pk=warehouse).first()
                avail = available_stock(instance, selected)
                label = f" at {selected}" if selected else " across warehouses"
                self.fields["quantity"].help_text = (
                    f"On-hand available now{label}: {avail}. Positive adds stock, negative reduces it."
                )

    def clean(self):
        cleaned = super().clean()
        qty = cleaned.get("quantity")
        txn = cleaned.get("transaction_type")
        if qty == 0:
            self.add_error("quantity", "Quantity cannot be zero.")
        if txn == StockTransaction.Type.DAMAGE and qty is not None and qty >= 0:
            self.add_error("quantity", "Damage must use a negative quantity (e.g. -2).")
        return cleaned


class MinStockLevelForm(TailwindFormMixin, forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.all(), widget=forms.HiddenInput
    )
    min_stock_level = forms.IntegerField(min_value=0, label="Min stock")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["min_stock_level"].widget.attrs["class"] = (
            "w-20 rounded border border-slate-300 px-2 py-1 text-sm"
        )
