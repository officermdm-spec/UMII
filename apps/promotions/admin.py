from django.contrib import admin

from apps.promotions.models import ProductOffer


@admin.register(ProductOffer)
class ProductOfferAdmin(admin.ModelAdmin):
    list_display = ("name", "offer_type", "value", "is_active", "start_date", "end_date")
    list_filter = ("is_active", "offer_type", "show_on_website")
    search_fields = ("name",)
