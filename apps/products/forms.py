import uuid

from django import forms

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


class ProductImageForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["image", "alt_text", "sort_order"]


class BrandForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Brand
        fields = ["name", "is_active"]
