from django.contrib import admin

from apps.products.models import Brand, Product, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sku",
        "barcode",
        "selling_price",
        "discount_percent",
        "stock_quantity",
        "is_active",
    )
    search_fields = ("name", "sku", "barcode")
    list_filter = ("is_active", "category", "discount_percent")
    inlines = [ProductImageInline]
    readonly_fields = ("stock_quantity", "barcode")


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    prepopulated_fields = {"slug": ("name",)}
