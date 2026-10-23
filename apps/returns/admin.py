from django.contrib import admin

from apps.returns.models import ReturnImage, ReturnItem, ReturnRequest


class ReturnItemInline(admin.TabularInline):
    model = ReturnItem
    extra = 0


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ("return_number", "order", "customer", "status")
    inlines = [ReturnItemInline]
