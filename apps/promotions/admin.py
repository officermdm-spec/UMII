from django.contrib import admin

from apps.promotions.models import ProductOffer, Promotion, PromotionUsage


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "discount_type", "is_active", "show_on_website", "start_date", "end_date")
    list_filter = ("is_active", "show_on_website", "discount_type")
    search_fields = ("name", "code")


@admin.register(ProductOffer)
class ProductOfferAdmin(admin.ModelAdmin):
    list_display = ("name", "offer_type", "value", "is_active", "start_date", "end_date")
    list_filter = ("is_active", "offer_type", "show_on_website")
    search_fields = ("name",)


@admin.register(PromotionUsage)
class PromotionUsageAdmin(admin.ModelAdmin):
    list_display = ("promotion", "customer", "order", "created_at")
