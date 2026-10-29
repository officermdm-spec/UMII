from datetime import timedelta
from decimal import Decimal

from django import forms
from django.db.models import F, Q, Sum
from django.utils import timezone

from apps.products.models import Product
from apps.promotions.models import ProductOffer
from config.forms import TailwindFormMixin


def promotable_products():
    return (
        Product.objects.filter(is_active=True)
        .annotate(
            on_hand=Sum(F("inventories__current_stock") - F("inventories__reserved_stock"))
        )
        .distinct()
        .order_by("name")
    )


class InventoryProductChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        qty = getattr(obj, "on_hand", None)
        if qty is None:
            qty = obj.stock_quantity
        return f"{obj.name} ({obj.sku}) · {qty} in stock"


def _stamp_datetime_fields(form, names=("start_date", "end_date")):
    now = timezone.localtime()
    if not form.instance.pk:
        form.fields["start_date"].initial = now.strftime("%Y-%m-%dT%H:%M")
        form.fields["end_date"].initial = (now + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M")
        return
    for name in names:
        value = getattr(form.instance, name, None)
        if value:
            form.initial[name] = timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


def _bind_product_queryset(form):
    products = promotable_products()
    if form.instance.pk:
        products = (
            Product.objects.filter(Q(pk__in=products) | Q(pk__in=form.instance.products.all()))
            .annotate(
                on_hand=Sum(F("inventories__current_stock") - F("inventories__reserved_stock"))
            )
            .distinct()
            .order_by("name")
        )
    form.fields["products"].queryset = products
    form.fields["products"].widget.attrs["class"] = "grid gap-2 text-sm"


class ProductOfferForm(TailwindFormMixin, forms.ModelForm):
    products = InventoryProductChoiceField(
        queryset=Product.objects.none(),
        required=True,
        widget=forms.SelectMultiple(attrs={"size": 1}),
        help_text="Select one or more products this sale should cover (Ctrl/Cmd-click to select multiple).",
    )

    class Meta:
        model = ProductOffer
        fields = [
            "name",
            "offer_type",
            "value",
            "buy_qty",
            "get_qty",
            "products",
            "start_date",
            "end_date",
            "is_active",
            "show_on_website",
        ]
        labels = {
            "name": "Offer name",
            "offer_type": "Offer type",
            "value": "Discount value",
            "buy_qty": "Buy quantity",
            "get_qty": "Get quantity",
            "products": "Applicable products",
            "start_date": "Starts",
            "end_date": "Ends",
            "is_active": "Active",
            "show_on_website": "Show on website",
        }
        widgets = {
            "start_date": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "end_date": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "offer_type": forms.Select,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _stamp_datetime_fields(self)
        _bind_product_queryset(self)
        if not self.instance.pk:
            self.fields["is_active"].initial = True
            self.fields["show_on_website"].initial = True
            self.fields["offer_type"].initial = ProductOffer.OfferType.PERCENTAGE
        self.fields["value"].help_text = "Used for percentage and fixed amount offers."
        self.fields["buy_qty"].help_text = "Only for Buy X Get Y. Example: buy 2."
        self.fields["get_qty"].help_text = "Only for Buy X Get Y. Example: get 1 free."
        self.fields["value"].required = False
        self.fields["buy_qty"].required = False
        self.fields["get_qty"].required = False
        for name in ("start_date", "end_date"):
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]

    def clean_value(self):
        value = self.cleaned_data.get("value")
        offer_type = self.data.get("offer_type") or self.cleaned_data.get("offer_type")
        if offer_type == ProductOffer.OfferType.BUY_X_GET_Y:
            return value or Decimal("0.00")
        if value is None or value <= 0:
            raise forms.ValidationError("Enter a discount greater than zero.")
        return value

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end <= start:
            self.add_error("end_date", "End date must be after the start date.")
        offer_type = cleaned.get("offer_type")
        value = cleaned.get("value")
        if offer_type == ProductOffer.OfferType.PERCENTAGE and value is not None and value > Decimal("100"):
            self.add_error("value", "Percentage cannot be more than 100.")
        if offer_type == ProductOffer.OfferType.BUY_X_GET_Y:
            if not cleaned.get("buy_qty") or not cleaned.get("get_qty"):
                self.add_error("buy_qty", "Enter how many items the customer must buy.")
                self.add_error("get_qty", "Enter how many items are free.")
        products = cleaned.get("products")
        if not products:
            self.add_error("products", "Select at least one product.")
        return cleaned
