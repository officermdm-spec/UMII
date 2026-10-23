from django.contrib import admin

from apps.purchases.models import GRN, GRNItem, ProductPurchaseHistory


class GRNItemInline(admin.TabularInline):
    model = GRNItem
    extra = 1


@admin.register(GRN)
class GRNAdmin(admin.ModelAdmin):
    list_display = ("grn_number", "vendor", "status", "grn_date")
    inlines = [GRNItemInline]


@admin.register(ProductPurchaseHistory)
class ProductPurchaseHistoryAdmin(admin.ModelAdmin):
    list_display = ("product", "vendor", "quantity", "purchase_rate", "purchased_at")
