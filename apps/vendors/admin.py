from django.contrib import admin

from apps.vendors.models import Vendor


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("company_name", "phone", "city", "is_active")
    search_fields = ("company_name", "phone")
