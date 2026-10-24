import uuid

from django import forms
from django.forms import inlineformset_factory
from django.utils.text import slugify

from apps.products.models import Brand, Product, ProductImage
from config.forms import TailwindFormMixin


class ProductForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "selling_price",
            "purchase_price",
            "category",
            "vendor",
            "brand",
            "size",
            "color",
            "unit",
            "discount_percent",
            "min_stock_level",
            "description",
        ]
        labels = {"min_stock_level": "Minimum stock level"}
        help_texts = {
            "min_stock_level": "Inventory shows Low when available stock is at or below this number."
        }

    def save(self, commit=True):
        if not self.instance.sku:
            self.instance.sku = f"SKU-{uuid.uuid4().hex[:12].upper()}"
        return super().save(commit=commit)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.variant_parent_id:
            self.fields.pop("size")
            self.fields.pop("color")


class ProductVariantForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "sku",
            "size",
            "color",
            "is_active",
        ]
        widgets = {"sku": forms.TextInput(attrs={"placeholder": "Auto-generated if blank"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sku"].required = False
        if not self.is_bound and not self.instance.pk:
            self.fields["is_active"].initial = True

    def has_changed(self):
        if not self.instance.pk:
            return any(
                (self.data.get(self.add_prefix(field)) or "").strip()
                for field in ("sku", "size", "color")
            )
        return super().has_changed()

    def clean_size(self):
        size = (self.cleaned_data.get("size") or "").strip()
        if not size:
            raise forms.ValidationError("Enter a size for this variant.")
        return size

    def save(self, commit=True):
        variant = super().save(commit=False)
        parent = variant.variant_parent
        variant.name = parent.name
        variant.category = parent.category
        variant.vendor = parent.vendor
        variant.brand = parent.brand
        variant.description = parent.description
        variant.image = parent.image
        variant.unit = parent.unit
        variant.tax_percent = parent.tax_percent
        variant.selling_price = parent.selling_price
        variant.purchase_price = parent.purchase_price
        variant.discount_percent = parent.discount_percent
        variant.min_stock_level = parent.min_stock_level
        if not variant.sku:
            suffix = "-".join(filter(None, (variant.size, variant.color)))
            base_sku = slugify(f"{parent.sku}-{suffix}").upper()[:50]
            variant.sku = base_sku
            if Product.objects.filter(sku=variant.sku).exclude(pk=variant.pk).exists():
                variant.sku = f"{base_sku[:42]}-{uuid.uuid4().hex[:6].upper()}"
        if commit:
            variant.save()
            self.save_m2m()
        return variant


class BaseProductVariantFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        seen = set()
        parent = self.instance
        if (
            parent.pk
            and not parent.size
            and parent.stock_quantity > 0
            and any(form.cleaned_data.get("size") for form in self.forms if hasattr(form, "cleaned_data"))
        ):
            raise forms.ValidationError(
                "Set the product's current stock size before adding size variants, so existing stock remains assigned to the right size."
            )
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            size = (form.cleaned_data.get("size") or "").strip().casefold()
            color = (form.cleaned_data.get("color") or "").strip().casefold()
            if not size:
                continue
            key = (size, color)
            if key in seen:
                raise forms.ValidationError(
                    "Each size and color combination can only be added once."
                )
            seen.add(key)


ProductVariantFormSet = inlineformset_factory(
    Product,
    Product,
    fk_name="variant_parent",
    form=ProductVariantForm,
    formset=BaseProductVariantFormSet,
    extra=1,
    can_delete=False,
)


class ProductImageForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "sort_order"]


class BrandForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Brand
        fields = ["name", "is_active"]
